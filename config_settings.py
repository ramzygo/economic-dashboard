"""
Configuration settings for the Economic Dashboard.
Controls offline mode and caching behavior.
"""

import os

# Offline mode settings
OFFLINE_MODE = os.getenv('ECONOMIC_DASHBOARD_OFFLINE', 'false').lower() == 'true'

# Cache settings
CACHE_DIR = 'data/cache'
CACHE_EXPIRY_HOURS = 24  # How long to keep cached data

# Yahoo Finance rate limiting
YFINANCE_RATE_LIMIT_DELAY = 0.5  # Seconds between requests
YFINANCE_BATCH_SIZE = 5  # Max tickers to fetch in one batch
YFINANCE_CACHE_HOURS = 24  # Cache Yahoo Finance data for 24 hours

# Data sources
DATA_SOURCES = {
    'fred': {
        'online': True,
        'offline_file': 'data/sample_fred_data.csv',
        'cache_file': f'{CACHE_DIR}/fred_cache'
    },
    'yfinance': {
        'online': True,
        'offline_dir': 'data/',
        'cache_dir': f'{CACHE_DIR}/yfinance/'
    },
    'world_bank': {
        'online': True,
        'offline_file': 'data/sample_world_bank_gdp.csv',
        'cache_file': f'{CACHE_DIR}/world_bank_cache'
    }
}

# Sample data settings
SAMPLE_DATA_AVAILABLE = {
    'fred': os.path.exists('data/sample_fred_data.csv'),
    'yfinance': any(f.startswith('sample_') and f.endswith('_data.csv')
                   for f in os.listdir('data/') if os.path.isfile(os.path.join('data', f))),
    'world_bank': os.path.exists('data/sample_world_bank_gdp.csv')
}

def is_offline_mode():
    """Check if offline mode is enabled."""
    return OFFLINE_MODE

def can_use_offline_data(source):
    """Check if offline data is available for a source."""
    return SAMPLE_DATA_AVAILABLE.get(source, False)

def get_cache_dir():
    """Get the cache directory path."""
    return CACHE_DIR

def ensure_cache_dir():
    """Ensure cache directory exists."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(f'{CACHE_DIR}/yfinance/', exist_ok=True)