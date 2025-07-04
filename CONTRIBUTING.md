# Contributing to Karaoke Maker

Thank you for considering contributing to Karaoke Maker! This document provides guidelines and instructions for contributing to the project.

## Code of Conduct

Please be respectful and considerate of others when contributing to this project.

## How to Contribute

### Reporting Bugs

If you find a bug, please create an issue with:

1. A clear title and description
2. Steps to reproduce the bug
3. Expected behavior vs actual behavior
4. Screenshots if applicable
5. System information (OS, Docker version, etc.)

### Suggesting Enhancements

For feature requests:

1. Clearly describe the feature
2. Explain why it would be valuable
3. Suggest how it might be implemented (optional)

### Pull Requests

1. Fork the repository
2. Create a new branch from `main`
3. Make your changes
4. Test your changes
5. Submit a pull request with a clear description

## Development Setup

1. Clone your fork:
   ```bash
   git clone https://github.com/your-username/karaoke-maker.git
   ```

2. Create a branch for your work:
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. Set up the development environment:
   ```bash
   cp .env.example .env
   # Edit .env with your development settings
   docker compose up -d
   ```

## Project Structure

The project is organized as a microservice architecture:

- **API**: REST API for file uploads and processing
- **Watcher**: Monitors directories for new files
- **Metadata**: Extracts and manages metadata
- **Splitter**: Handles audio separation
- **Packager**: Processes and finalizes output files
- **Dashboard**: User interface

## Testing

Please ensure all your changes include appropriate tests:

```bash
docker compose -f docker-compose.test.yml up
```

## Coding Standards

- Follow PEP 8 for Python code
- Use ESLint for JavaScript/TypeScript
- Write meaningful commit messages
- Document new features or changes

## License

By contributing, you agree that your contributions will be licensed under the project's MIT License.
