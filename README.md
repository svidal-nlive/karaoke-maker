# Karaoke Maker

A containerized pipeline for creating karaoke tracks by separating and remixing audio stems.

## Features

- JWT-based authentication with role-based access control and dynamic JWT secrets
- Upload MP3 files via REST API or file system watcher
- Extract and preserve audio metadata and cover art
- Separate audio into stems using Spleeter
- Customize which stems to include in the final mix
- Apply original metadata and cover art to the output file
- Organize output in a library structure (Artist/Album/Song)
- Modern React dashboard with password change functionality
- OpenAPI/Swagger documentation available at `/docs/`
- CORS configured for custom domains
- Dockerized deployment with separate services

## Architecture

The system consists of the following components:

- **API Service**: Handles file uploads, authentication, and Swagger docs
- **Watcher**: Monitors a directory for new files
- **Metadata Extractor**: Extracts metadata and cover art
- **Stem Splitter**: Separates audio into stems using Spleeter
- **Packager**: Merges selected stems and applies metadata
- **Dashboard**: Web UI for managing jobs and settings
- **Redis**: Message broker for inter-service communication

## Getting Started

### Prerequisites

- Docker and Docker Compose
- A machine with sufficient resources for audio processing
- Cloudflare tunnel configured (if using custom domains)

### Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/karaoke-maker.git
cd karaoke-maker
## Usage

### Adding Files for Processing

Files can be added in two ways:

1. **Via the dashboard**:
   - Log in to the dashboard
   - Use the upload function to add files

2. **Via the filesystem**:
   - Add MP3 files to the `pipeline-data/input` directory
   - The watcher will automatically detect and process them

### Processing Pipeline

1. Files are detected by the watcher or uploaded via API
2. Metadata and cover art are extracted
3. Audio is split into stems (vocals, drums, bass, other)
4. Selected stems are merged (typically excluding vocals for karaoke)
5. Metadata and cover art are applied to the output file
6. Output is organized by artist/album in the output directory
7. Temporary files are cleaned up

### Configuration

The system can be configured through environment variables in the `.env` file:

- `STEMS`: Number of stems to split into (2, 4, or 5)
- `CLEAN_INTERMEDIATE`: Whether to clean up temporary files after processing
- `MAX_RETRIES`: Number of retry attempts for failed jobs
- `FETCH_COVER_ART`: Whether to fetch missing cover art from external sources

## Development

### Running Tests

```bash
docker compose -f docker-compose.test.yml up
```

### Customizing the Dashboard

The dashboard is built with React and can be customized:

```bash
cd dashboard
npm install
npm run dev
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Spleeter by Deezer for audio separation
- All contributors and open source libraries used
# Edit .env with your preferred settings
# Key settings:
# - API_BASE_URL: Set to your API domain (e.g., https://kapi.vectorhost.net/api)
# - TUNNEL_TOKEN: Your Cloudflare tunnel token
```

3. Start the services:

```bash
docker-compose up -d
```

4. Access the dashboard at your configured domain (e.g., https://mydash.vectorhost.net)

### Default Credentials

- Username: `admin`
- Password: `admin`

**Important**: You will be prompted to change these credentials on first login for security.

## Usage

### Web UI

1. Log in to the dashboard with default credentials (admin/admin)
2. Change your username and password when prompted
3. Upload MP3 files through the upload page
4. Monitor job status on the dashboard
5. Configure settings (admin only)

### API Documentation

Visit `/docs/` on your API domain to access the interactive Swagger UI documentation where you can test all endpoints.

### File System

1. Place MP3 files in the `pipeline-data/input` directory
2. Files will be automatically processed
3. Find the output files in the `pipeline-data/output` directory

## Configuration

The system can be configured through environment variables in the `.env` file:

### Key Settings

- `API_BASE_URL`: The base URL for your API service
- `JWT_SECRET`: Automatically generated secure JWT secret (or set your own)
- `ADMIN_PASSWORD`: Default admin password (change on first login)
- `SPLITTER_TYPE`: The stem separation tool to use (default: "SPLEETER")
- `STEMS`: Number of stems to extract (2, 4, or 5)
- `STEM_TYPE`: Default stems to include
- `TUNNEL_TOKEN`: Cloudflare tunnel token for public access

### CORS Configuration

The API is pre-configured to accept requests from:
- `https://mydash.vectorhost.net` (dashboard)
- `https://kapi.vectorhost.net` (API)
- `http://localhost:3020` (local development)
- `http://localhost:3000` (local development)

## Directory Structure

- `pipeline-data/input`: Input files
- `pipeline-data/output`: Processed output files
- `pipeline-data/archive`: Archived input files
- `pipeline-data/error`: Files that failed processing
- `pipeline-data/logs`: Log files
- `pipeline-data/metadata`: Extracted metadata
- `pipeline-data/queue`: Files in the processing queue
- `pipeline-data/stems`: Extracted stems

## Security Features

- Dynamic JWT secret generation
- Password hashing with SHA-256
- Mandatory password change for default credentials
- CORS protection for specific domains
- Role-based access control (admin vs standard users)

## Development

### Dashboard Development

```bash
cd dashboard
npm install
npm run dev
```

### API Development

The API includes comprehensive Swagger documentation accessible at `/docs/`.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
