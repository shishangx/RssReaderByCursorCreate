from flask import Flask, render_template, request, jsonify, url_for, redirect, flash
from flask_sqlalchemy import SQLAlchemy
import feedparser
import ollama
import uuid
import logging
import requests
from html.parser import HTMLParser
import re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from sqlalchemy import desc
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

app = Flask(__name__, static_url_path='/static')
app.secret_key = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///rss_reader.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=5)

class Feed(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    verify_ssl = db.Column(db.Boolean, default=True)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

class Entry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    feed_id = db.Column(db.String(36), db.ForeignKey('feed.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    link = db.Column(db.String(500), nullable=False)
    content = db.Column(db.Text, nullable=True)
    summary = db.Column(db.Text, nullable=True)
    published = db.Column(db.DateTime, nullable=True)

with app.app_context():
    db.create_all()

class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs= True
        self.text = []
    def handle_data(self, d):
        self.text.append(d)
    def get_data(self):
        return ''.join(self.text)

def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()

@app.route('/')
def index():
    feeds = Feed.query.all()
    feeds_dict = {feed.id: feed for feed in feeds}
    return render_template('index.html', feeds=feeds_dict)

def get_rss_feed(url, verify_ssl=True):
    try:
        logger.info(f"Fetching RSS feed from URL: {url}")
        response = requests.get(url, verify=verify_ssl, timeout=10)
        response.raise_for_status()
        feed = feedparser.parse(response.content)
        if feed.bozo:
            logger.error(f"Error parsing feed {url}: {feed.bozo_exception}")
            raise Exception(f"Error parsing feed: {feed.bozo_exception}")
        logger.info(f"Successfully fetched and parsed feed. Found {len(feed.entries)} entries.")
        return feed
    except requests.RequestException as e:
        logger.error(f"Error fetching feed {url}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error processing feed {url}: {str(e)}")
        raise

def update_feed_entries(app, feed):
    with app.app_context():
        logger.info(f"Updating entries for feed: {feed.title}")
        try:
            feed_data = get_rss_feed(feed.url, feed.verify_ssl)
            logger.info(f"Retrieved {len(feed_data.entries)} entries from RSS feed")
            new_entries_count = 0
            for entry in feed_data.entries:
                existing_entry = Entry.query.filter_by(feed_id=feed.id, link=entry.link).first()
                if not existing_entry:
                    content = entry.get('content', [{}])[0].get('value', '') or entry.get('summary', '')
                    new_entry = Entry(
                        feed_id=feed.id,
                        title=entry.get('title', 'Untitled'),
                        link=entry.get('link', '#'),
                        content=content,
                        published=datetime(*entry.get('published_parsed', datetime.utcnow().timetuple())[:6])
                    )
                    db.session.add(new_entry)
                    new_entries_count += 1
            feed.last_updated = datetime.utcnow()
            db.session.commit()
            logger.info(f"Finished updating entries for feed: {feed.title}. Added {new_entries_count} new entries.")
        except Exception as e:
            logger.error(f"Error updating feed {feed.title}: {str(e)}")
            db.session.rollback()

@app.route('/feed', methods=['POST'])
def add_feed():
    url = request.form['url']
    verify_ssl = request.form.get('verify_ssl', 'on') == 'on'

    try:
        logger.info(f"Adding new feed: {url}")
        feed_data = get_rss_feed(url, verify_ssl)
        feed_id = str(uuid.uuid4())
        new_feed = Feed(id=feed_id, title=feed_data.feed.get('title', 'Untitled Feed'), url=url, verify_ssl=verify_ssl)
        db.session.add(new_feed)
        db.session.commit()

        # 在后台更新 feed 条目并等待完成
        future = executor.submit(update_feed_entries, app, new_feed)
        future.result()  # 等待任务完成

        flash('Feed added successfully!', 'success')
    except Exception as e:
        logger.error(f"Error adding feed: {str(e)}")
        flash(f"Error adding feed: {str(e)}", 'error')

    return redirect(url_for('index'))

@app.route('/feed/<feed_id>')
def show_feed(feed_id):
    try:
        feed = Feed.query.get_or_404(feed_id)
        logger.info(f"Showing feed: {feed.title}")

        if datetime.utcnow() - feed.last_updated > timedelta(minutes=30):
            logger.info(f"Feed {feed.title} is outdated. Updating entries...")
            update_feed_entries(app, feed)
        else:
            logger.info(f"Feed {feed.title} is up to date. Last updated: {feed.last_updated}")

        entries = Entry.query.filter_by(feed_id=feed_id).order_by(desc(Entry.published)).all()
        logger.info(f"Found {len(entries)} entries for feed: {feed.title}")

        if not entries:
            logger.warning(f"No entries found for feed: {feed.title}. Forcing update...")
            update_feed_entries(app, feed)
            entries = Entry.query.filter_by(feed_id=feed_id).order_by(desc(Entry.published)).all()
            logger.info(f"After forced update, found {len(entries)} entries for feed: {feed.title}")

        return render_template('feed.html', feed=feed, entries=entries)
    except Exception as e:
        logger.error(f"Error in show_feed: {str(e)}")
        flash(f"Error showing feed: {str(e)}", 'error')
        return redirect(url_for('index'))

@app.route('/feed/<feed_id>/delete', methods=['POST'])
def delete_feed(feed_id):
    feed = Feed.query.get_or_404(feed_id)
    Entry.query.filter_by(feed_id=feed_id).delete()
    db.session.delete(feed)
    db.session.commit()
    flash('Feed deleted successfully!', 'success')
    return redirect(url_for('index'))

@app.route('/feed/<feed_id>/edit', methods=['GET', 'POST'])
def edit_feed(feed_id):
    feed = Feed.query.get_or_404(feed_id)

    if request.method == 'POST':
        new_url = request.form['url']
        verify_ssl = request.form.get('verify_ssl', 'on') == 'on'
        try:
            feed_data = get_rss_feed(new_url, verify_ssl)
            feed.url = new_url
            feed.verify_ssl = verify_ssl
            feed.title = feed_data.feed.get('title', 'Untitled Feed')
            db.session.commit()
            update_feed_entries(app, feed)
            flash('Feed updated successfully!', 'success')
        except Exception as e:
            flash(f"Error updating feed: {str(e)}", 'error')
        return redirect(url_for('index'))

    return render_template('edit_feed.html', feed=feed)

def summarize_article(text):
    try:
        response = ollama.chat(model='gemma2:2b', messages=[
            {
                'role': 'user',
                'content': f"Summarize the following text in about 50 words, without including any introductory phrase: {text}",
            },
        ])
        return response['message']['content']
    except Exception as e:
        logger.error(f"Error summarizing article: {str(e)}")
        return text[:200] + '...'  # 如果摘要生成失败，返回文本的前200个字符

def process_content(content):
    soup = BeautifulSoup(content, 'html.parser')
    processed_content = []

    for element in soup.find_all(['h3', 'ul', 'p']):
        if element.name == 'h3':
            processed_content.append(f"<h3>{element.text.strip()}</h3>")
        elif element.name == 'ul':
            items = []
            for li in element.find_all('li'):
                item_content = []
                for child in li.children:
                    if child.name == 'a':
                        href = child.get('href', '#')
                        item_content.append(f'<a href="{href}" target="_blank">{child.text}</a>')
                    else:
                        item_content.append(str(child))
                items.append(f"<li>{''.join(item_content)}</li>")
            processed_content.append("<ul>" + "".join(items) + "</ul>")
        elif element.name == 'p':
            p_content = []
            for child in element.children:
                if child.name == 'a':
                    href = child.get('href', '#')
                    p_content.append(f'<a href="{href}" target="_blank">{child.text}</a>')
                else:
                    p_content.append(str(child))
            processed_content.append(f"<p>{''.join(p_content)}</p>")

    return "\n".join(processed_content)

@app.route('/article/<feed_id>/<int:article_id>')
def show_article(feed_id, article_id):
    try:
        entry = Entry.query.filter_by(feed_id=feed_id).order_by(Entry.published.desc()).offset(article_id).first_or_404()
        if not entry.summary:
            entry.summary = summarize_article(strip_tags(entry.content))
            db.session.commit()
        processed_content = process_content(entry.content)
        return render_template('article.html', article=entry, content=processed_content)
    except Exception as e:
        logger.error(f"Error processing article: {str(e)}")
        flash("Error processing article content. Please try again later.", "error")
        return redirect(url_for('show_feed', feed_id=feed_id))

def generate_missing_summaries(feed_id):
    entries = Entry.query.filter_by(feed_id=feed_id, summary=None).all()
    for entry in entries:
        entry.summary = summarize_article(strip_tags(entry.content))[:200] + '...'
    db.session.commit()

@app.route('/feeds/delete', methods=['POST'])
def delete_feeds():
    feed_ids = request.form.getlist('feed_ids')
    if feed_ids:
        try:
            for feed_id in feed_ids:
                feed = Feed.query.get(feed_id)
                if feed:
                    Entry.query.filter_by(feed_id=feed_id).delete()
                    db.session.delete(feed)
            db.session.commit()
            flash(f'{len(feed_ids)} feed(s) deleted successfully!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error deleting feeds: {str(e)}', 'error')
    else:
        flash('No feeds selected for deletion', 'warning')
    return redirect(url_for('index'))

@app.route('/refresh_feed/<feed_id>', methods=['POST'])
def refresh_feed(feed_id):
    try:
        if feed_id == 'all':
            feeds = Feed.query.all()
            for feed in feeds:
                update_feed_entries(app, feed)
            flash('All feeds refreshed successfully!', 'success')
        else:
            feed = Feed.query.get_or_404(feed_id)
            update_feed_entries(app, feed)
            flash(f'Feed "{feed.title}" refreshed successfully!', 'success')
    except Exception as e:
        logger.error(f"Error refreshing feed(s): {str(e)}")
        flash(f'Error refreshing feed(s): {str(e)}', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5001)