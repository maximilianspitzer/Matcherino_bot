# Contributing to Matcherino Bot

Thank you for considering contributing to the Matcherino Bot project! Here's how you can help.

## Code of Conduct

By participating in this project, you agree to be respectful and considerate to all contributors.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check the existing issues to see if the problem has already been reported. When you are creating a bug report, please include as many details as possible:

- A clear and descriptive title
- Steps to reproduce the issue
- Expected behavior
- Actual behavior
- Screenshots or code snippets (if applicable)
- Environment details (OS, Python version, etc.)

### Suggesting Enhancements

Enhancement suggestions are always welcome. Please provide:

- A clear and descriptive title
- A detailed description of the proposed enhancement
- An explanation of why this enhancement would be useful
- Example code or mock-ups if applicable

### Pull Requests

1. Fork the repository
2. Create a new branch for your feature or bugfix
3. Commit your changes
4. Push to your branch
5. Open a pull request

#### Pull Request Guidelines

- Follow the existing code style
- Update documentation if necessary
- Add tests for new features
- Ensure all tests are passing
- Make sure the code lints without errors
- Reference any relevant issues in your PR description

## Development Setup

1. Fork and clone the repository
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set up your environment variables in a `.env` file (see `.env.example`)
5. Run the bot locally:
   ```bash
   python bot.py
   ```

## Testing

- We use the standard `unittest` module for testing
- Run tests with `python -m unittest discover`
- Please write tests for new features

## Documentation

- Update the README.md with details of changes to the interface
- Update the UNRAID.md with any deployment changes

## Questions?

Feel free to open an issue with your question. 