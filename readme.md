# RSS Reader

RSS Reader is a web application built with Flask that allows users to manage and read RSS feeds. It provides a simple and intuitive interface for adding, refreshing, and viewing RSS feed content.

## Features

- Add and manage multiple RSS feeds
- Automatic feed updates
- Manual refresh option for individual feeds or all feeds at once
- View feed entries with summarized content
- SSL verification toggle for feed sources
- Delete individual or multiple feeds
- Responsive design for various screen sizes

## Technologies Used

- Python 3.x
- Flask
- SQLAlchemy
- BeautifulSoup4
- Feedparser
- Ollama (for article summarization)
- Docker and Docker Compose

## Setup and Installation

### Local Development

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/rss-reader.git
   cd rss-reader
   ```

2. Set up a virtual environment (optional but recommended):
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
   ```

3. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

4. Run the application:
   ```
   python app.py
   ```

5. Open a web browser and navigate to `http://localhost:5001` to use the RSS Reader.

### Docker Deployment

1. Make sure you have Docker and Docker Compose installed on your system.

2. Clone the repository:
   ```
   git clone https://github.com/yourusername/rss-reader.git
   cd rss-reader
   ```

3. Build and start the Docker containers:
   ```
   docker-compose up -d --build
   ```

4. The application will be available at `http://localhost:5001`.

5. To stop the containers:
   ```
   docker-compose down
   ```

## Usage

1. **Adding a Feed**: Enter the RSS feed URL in the input field at the top of the page and click "Add Feed".
2. **Viewing Feed Entries**: Click on a feed title to view its entries.
3. **Refreshing Feeds**: Use the "Refresh All Feeds" button or individual feed refresh buttons to update feed content.
4. **Deleting Feeds**: Select feeds using checkboxes and click "Delete Selected" to remove them.
5. **Editing Feeds**: Click the "Edit" button next to a feed to modify its URL or SSL verification setting.

## Docker Compose Configuration

The `docker-compose.yml` file defines the services needed to run the RSS Reader application:

- `web`: The Flask application container
- `db`: A SQLite database volume for persistent storage

You can modify the `docker-compose.yml` file to change port mappings, environment variables, or add additional services as needed.

## Contributing

Contributions to the RSS Reader project are welcome! Please feel free to submit a Pull Request.

## License

This project is open source and available under the [MIT License](LICENSE).
