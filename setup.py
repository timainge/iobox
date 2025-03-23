from setuptools import setup, find_packages

setup(
    name="iobox",
    version="0.1.0",
    description="Gmail to Markdown Converter",
    author="Tim",
    author_email="tim@goodcollective.com.au",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.8",
    install_requires=[
        "google-api-python-client",
        "google-auth-httplib2",
        "google-auth-oauthlib",
        "typer",
        "python-dotenv",
    ],
    entry_points={
        "console_scripts": [
            "iobox=iobox.cli:app",
        ],
    },
)
