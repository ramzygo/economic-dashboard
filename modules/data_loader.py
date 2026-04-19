"""
Data loading module for Economic Dashboard.
Handles all data fetching from FRED and Yahoo Finance with DuckDB caching and offline support.
"""

import streamlit as st
import pandas as pd
import yfinance as yf
from pandas_datareader import data as pdr
from datetime import datetime, timedelta
import json
import os
import time
from typing import Optional
from config_settings import (
    is_offline_mode, can_use_offline_data, get_cache_dir,
    ensure_cache_dir, CACHE_EXPIRY_HOURS, YFINANCE_RATE_LIMIT_DELAY,
    YFINANCE_BATCH_SIZE, YFINANCE_CACHE_HOURS
)
from modules.auth.credentials_manager import get_credentials_manager

# Import DuckDB database functions
try:
    from modules.database import (
        get_db_connection,
        get_fred_series,
        get_stock_ohlcv,
        insert_fred_data,
        insert_stock_data,
        insert_options_data
    )
    DUCKDB_AVAILABLE = True
except ImportError:
    DUCKDB_AVAILABLE = False
    st.warning("DuckDB database module not available. Using legacy pickle caching.")


# Configure proxy if available (for GitHub Actions IP rotation)
def _setup_proxy():
    """Configure proxy settings from environment variables."""
    proxy_url = os.environ.get('PROXY_URL')
    if proxy_url:
        # Set yfinance session with proxy
        import requests
        session = requests.Session()
        session.proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        # Note: yfinance doesn't easily support custom sessions,
        # but this sets up the environment for requests-based calls
        os.environ['HTTP_PROXY'] = proxy_url
        os.environ['HTTPS_PROXY'] = proxy_url
        return True
    return False

# Initialize proxy on module load
_PROXY_ENABLED = _setup_proxy()


def _cache_meta_path(cache_file: str) -> str:
    return cache_file + '.meta.json'


def _cache_data_path(cache_file: str) -> str:
    return cache_file + '.parquet'


def _load_cached_data(cache_file: str, max_age_hours: int | None = None) -> pd.DataFrame | dict | None:
    """Load data from cache if it exists and is not expired."""
    meta_path = _cache_meta_path(cache_file)
    if not os.path.exists(meta_path):
        return None

    try:
        with open(meta_path, 'r') as f:
            meta = json.load(f)

        cache_time = datetime.fromisoformat(meta['timestamp'])
        expiry_hours = max_age_hours if max_age_hours is not None else CACHE_EXPIRY_HOURS
        if datetime.now() - cache_time > timedelta(hours=expiry_hours):
            return None

        data_path = _cache_data_path(cache_file)
        if meta.get('type') == 'dataframe' and os.path.exists(data_path):
            return pd.read_parquet(data_path)
        elif meta.get('type') == 'json':
            return meta.get('data')
    except Exception:
        return None

    return None


def _save_cached_data(cache_file: str, data):
    """Save data to cache using JSON metadata + parquet for DataFrames."""
    ensure_cache_dir()
    try:
        meta_path = _cache_meta_path(cache_file)
        if isinstance(data, pd.DataFrame):
            data.to_parquet(_cache_data_path(cache_file))
            meta = {'timestamp': datetime.now().isoformat(), 'type': 'dataframe'}
        else:
            meta = {'timestamp': datetime.now().isoformat(), 'type': 'json', 'data': data}
        with open(meta_path, 'w') as f:
            json.dump(meta, f, default=str)
    except Exception as e:
        st.warning(f"Could not save cache: {e}")


def _load_offline_fred_data(series_ids: dict) -> pd.DataFrame:
    """Load FRED data from offline sample file."""
    try:
        if not can_use_offline_data('fred'):
            st.warning("Offline FRED data not available")
            return pd.DataFrame()

        df = pd.read_csv('data/sample_fred_data.csv', index_col=0, parse_dates=True)

        # Filter to requested series
        available_series = [sid for sid in series_ids.values() if sid in df.columns]
        if not available_series:
            st.warning("Requested FRED series not available in offline data")
            return pd.DataFrame()

        result_df = df[available_series].copy()
        # Rename columns back to descriptive names
        reverse_mapping = {v: k for k, v in series_ids.items()}
        result_df = result_df.rename(columns=reverse_mapping)

        return result_df
    except Exception as e:
        st.error(f"Error loading offline FRED data: {e}")
        return pd.DataFrame()


def _load_offline_yfinance_data(tickers: dict, period: str = "5y") -> dict:
    """Load Yahoo Finance data from offline sample files."""
    try:
        if not can_use_offline_data('yfinance'):
            st.warning("Offline Yahoo Finance data not available")
            return {}

        result = {}
        for name, ticker in tickers.items():
            filename = f"data/sample_{ticker.replace('^', '')}_data.csv"
            if os.path.exists(filename):
                df = pd.read_csv(filename, index_col=0, parse_dates=True)
                result[name] = df
            else:
                st.warning(f"Offline data for {ticker} not available")

        return result
    except Exception as e:
        st.error(f"Error loading offline Yahoo Finance data: {e}")
        return {}


@st.cache_data(ttl=3600)
def load_fred_data(series_ids: dict) -> pd.DataFrame:
    """
    Load economic data from FRED database.

    Args:
        series_ids: Dictionary with descriptive names as keys and FRED series IDs as values

    Returns:
        DataFrame with DatetimeIndex and columns for each series
    """
    # Check offline mode first
    if is_offline_mode():
        return _load_offline_fred_data(series_ids)

    # Try DuckDB first if available
    if DUCKDB_AVAILABLE and 'get_fred_series' in globals():
        try:
            # Get data from DuckDB
            series_list = list(series_ids.values())
            db_data = get_fred_series(series_list)
            
            if not db_data.empty:
                # Convert from long format to wide format
                result = db_data.pivot(index='date', columns='series_id', values='value')
                result.index = pd.to_datetime(result.index)
                
                # Rename columns back to descriptive names
                reverse_mapping = {v: k for k, v in series_ids.items()}
                result = result.rename(columns=reverse_mapping)
                
                return result
        except Exception as e:
            st.warning(f"Could not load from DuckDB: {e}. Falling back to API.")

    # First, try to load from the centralized cache (updated daily by automation)
    centralized_cache = f"{get_cache_dir()}/fred_all_series.pkl"
    if os.path.exists(centralized_cache):
        try:
            cached_data = _load_cached_data(centralized_cache)
            if cached_data is not None and isinstance(cached_data, pd.DataFrame):
                # Filter to requested series
                available_series = [name for name in series_ids.keys() if name in cached_data.columns]
                if available_series:
                    return cached_data[available_series].copy()
        except Exception as e:
            st.warning(f"Could not load from centralized cache: {e}")

    # Fallback: Try to load from individual cache
    cache_key = str(sorted(series_ids.items()))
    cache_file = f"{get_cache_dir()}/fred_{hash(cache_key)}.pkl"
    cached_data = _load_cached_data(cache_file)
    if cached_data is not None and isinstance(cached_data, pd.DataFrame):
        return cached_data

    # Load from API
    try:
        # Get FRED API key from credentials manager
        creds_manager = get_credentials_manager()
        fred_api_key = creds_manager.get_api_key('fred')
        
        data_frames = {}
        for name, series_id in series_ids.items():
            try:
                # Use API key if available
                if fred_api_key:
                    df = pdr.DataReader(series_id, 'fred', start='2000-01-01', api_key=fred_api_key)
                else:
                    # Fallback to unauthenticated access
                    df = pdr.DataReader(series_id, 'fred', start='2000-01-01')
                
                if not df.empty:
                    data_frames[name] = df.iloc[:, 0]
            except Exception as e:
                st.warning(f"Could not load {name} ({series_id}): {str(e)}")
                continue

        if data_frames:
            result = pd.DataFrame(data_frames)
            # Save to cache
            _save_cached_data(cache_file, result)
            return result
        else:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading FRED data: {str(e)}")
        # Fallback to offline data if available
        if can_use_offline_data('fred'):
            st.info("Falling back to offline data")
            return _load_offline_fred_data(series_ids)
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_yfinance_data(tickers: dict, period: str = "5y") -> dict:
    """
    Load market data from Yahoo Finance with rate limiting and smart caching.

    Args:
        tickers: Dictionary with descriptive names as keys and ticker symbols as values
        period: Time period to fetch (e.g., '1y', '5y', '10y')

    Returns:
        Dictionary of DataFrames, one for each ticker
    """
    # Check offline mode first
    if is_offline_mode():
        return _load_offline_yfinance_data(tickers, period)

    # Try DuckDB first if available
    if DUCKDB_AVAILABLE:
        try:
            # Get data from DuckDB
            ticker_list = list(tickers.values())
            db_data = get_stock_ohlcv(ticker_list)
            
            if not db_data.empty:
                # Convert to expected format (dict of DataFrames)
                result = {}
                for ticker in ticker_list:
                    ticker_data = db_data[db_data['ticker'] == ticker].copy()
                    if not ticker_data.empty:
                        # Set date as index and select OHLCV columns
                        ticker_data = ticker_data.set_index('date')
                        ticker_data = ticker_data[['open', 'high', 'low', 'close', 'volume']]
                        if 'adj_close' in ticker_data.columns:
                            ticker_data['Adj Close'] = ticker_data['adj_close']
                        
                        # Find the descriptive name for this ticker
                        name = next((k for k, v in tickers.items() if v == ticker), ticker)
                        result[name] = ticker_data
                
                if result:
                    return result
        except Exception as e:
            st.warning(f"Could not load from DuckDB: {e}. Falling back to API.")

    # First, try to load from the centralized cache (updated daily by automation)
    centralized_cache = f"{get_cache_dir()}/yfinance_all_tickers.pkl"
    if os.path.exists(centralized_cache):
        try:
            cached_data = _load_cached_data(centralized_cache, max_age_hours=YFINANCE_CACHE_HOURS)
            if cached_data is not None and isinstance(cached_data, dict):
                # Filter to requested tickers
                available_tickers = {name: data for name, data in cached_data.items() if name in tickers.keys()}
                if available_tickers:
                    return available_tickers
        except Exception as e:
            st.warning(f"Could not load from centralized cache: {e}")

    # Fallback: Try to load from individual cache with 24-hour expiry
    cache_key = str(sorted(tickers.items())) + period
    cache_file = f"{get_cache_dir()}/yfinance_{hash(cache_key)}.pkl"
    cached_data = _load_cached_data(cache_file, max_age_hours=YFINANCE_CACHE_HOURS)
    if cached_data is not None and isinstance(cached_data, dict):
        # Check if we have all requested tickers in cache
        if all(name in cached_data for name in tickers.keys()):
            return cached_data

    # Load from API with rate limiting
    try:
        result = {}
        ticker_list = list(tickers.items())
        total_tickers = len(ticker_list)
        
        # Process in batches to avoid rate limiting
        for i in range(0, total_tickers, YFINANCE_BATCH_SIZE):
            batch = ticker_list[i:i + YFINANCE_BATCH_SIZE]
            
            for name, ticker in batch:
                try:
                    # Add delay between requests to respect rate limits
                    if i > 0 or result:  # Don't delay on first request
                        time.sleep(YFINANCE_RATE_LIMIT_DELAY)
                    
                    # Download with auto_adjust=True to avoid FutureWarning
                    data = yf.download(ticker, period=period, progress=False, auto_adjust=True)
                    
                    if data is not None and not data.empty:
                        # Handle MultiIndex columns for single ticker
                        if isinstance(data.columns, pd.MultiIndex):
                            data.columns = data.columns.get_level_values(0)
                        result[name] = data
                    else:
                        st.warning(f"No data available for {name} ({ticker})")
                except Exception as e:
                    error_msg = str(e)
                    # Provide more specific error messages
                    if "Rate limit" in error_msg or "Too Many Requests" in error_msg:
                        st.warning(f"⏱️ Rate limited on {name} ({ticker}). Using cached data if available.")
                        # Try to load from any available cache, even if expired
                        old_cached = _load_cached_data(cache_file, max_age_hours=168)  # 1 week
                        if old_cached is not None and isinstance(old_cached, dict) and name in old_cached:
                            result[name] = old_cached[name]
                            st.info(f"Using cached data for {name} (may be up to 1 week old)")
                    elif "No objects to concatenate" in error_msg:
                        st.warning(f"Could not load {name} ({ticker}): Data not available for this period")
                    else:
                        st.warning(f"Could not load {name} ({ticker}): {error_msg}")
                    continue

        if result:
            # Save to cache with current timestamp
            _save_cached_data(cache_file, result)

        return result
    except Exception as e:
        st.error(f"Error loading Yahoo Finance data: {str(e)}")
        # Fallback to offline data if available
        if can_use_offline_data('yfinance'):
            st.info("Falling back to offline data")
            return _load_offline_yfinance_data(tickers, period)
        return {}


@st.cache_data(ttl=3600)
def get_yield_curve_data() -> pd.DataFrame:
    """
    Fetch US Treasury yield data and calculate spread.
    
    Returns:
        DataFrame with 10-Year yield, 2-Year yield, and spread
    """
    try:
        series_ids = {
            '10-Year': 'DGS10',
            '2-Year': 'DGS2'
        }
        
        df = load_fred_data(series_ids)
        
        if not df.empty and '10-Year' in df.columns and '2-Year' in df.columns:
            df['Spread'] = df['10-Year'] - df['2-Year']
            return df.dropna()
        else:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"Error calculating yield curve: {str(e)}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def load_world_bank_gdp() -> pd.DataFrame:
    """
    Load World Bank GDP growth data.
    Note: This is a simplified version. For production, use World Bank API.

    Returns:
        DataFrame with GDP growth by country
    """
    # Check offline mode first
    if is_offline_mode():
        try:
            if not can_use_offline_data('world_bank'):
                st.warning("Offline World Bank data not available")
                return pd.DataFrame()

            df = pd.read_csv('data/sample_world_bank_gdp.csv')
            return df
        except Exception as e:
            st.error(f"Error loading offline World Bank data: {e}")
            return pd.DataFrame()

    # Try to load from cache
    cache_file = f"{get_cache_dir()}/world_bank_gdp.pkl"
    cached_data = _load_cached_data(cache_file)
    if cached_data is not None and isinstance(cached_data, pd.DataFrame):
        return cached_data

    # Load from API (simplified version)
    try:
        # For now, return a simple dataset
        # In production, integrate with World Bank API or use a CSV file
        countries = ['United States', 'China', 'Germany', 'Japan', 'United Kingdom',
                     'France', 'India', 'Brazil', 'Canada', 'South Korea']
        gdp_growth = [2.1, 5.2, 0.9, 1.0, 1.3, 1.1, 6.8, 1.2, 1.5, 2.6]

        df = pd.DataFrame({
            'Country': countries,
            'GDP Growth (%)': gdp_growth,
            'ISO3': ['USA', 'CHN', 'DEU', 'JPN', 'GBR', 'FRA', 'IND', 'BRA', 'CAN', 'KOR']
        })

        # Save to cache
        _save_cached_data(cache_file, df)

        return df
    except Exception as e:
        st.error(f"Error loading World Bank data: {str(e)}")
        # Fallback to offline data if available
        if can_use_offline_data('world_bank'):
            st.info("Falling back to offline data")
            try:
                df = pd.read_csv('data/sample_world_bank_gdp.csv')
                return df
            except Exception:
                return pd.DataFrame()
        return pd.DataFrame()


@st.cache_data(ttl=3600)
def get_latest_value(series_id: str) -> float | None:
    """
    Get the most recent value for a FRED series.

    Args:
        series_id: FRED series ID

    Returns:
        Latest value as float
    """
    # Check offline mode first
    if is_offline_mode():
        try:
            if not can_use_offline_data('fred'):
                st.warning("Offline FRED data not available")
                return None

            df = pd.read_csv('data/sample_fred_data.csv', index_col=0, parse_dates=True)
            if series_id in df.columns and not df[series_id].empty:
                return float(df[series_id].iloc[-1])
            return None
        except Exception as e:
            st.error(f"Error loading offline FRED data: {e}")
            return None

    # Try to load from cache
    cache_file = f"{get_cache_dir()}/fred_latest_{series_id}.pkl"
    cached_data = _load_cached_data(cache_file)
    if cached_data is not None and isinstance(cached_data, (int, float)):
        return float(cached_data)

    # Load from API
    try:
        # Get FRED API key from credentials manager
        creds_manager = get_credentials_manager()
        fred_api_key = creds_manager.get_api_key('fred')
        
        # Use API key if available
        if fred_api_key:
            df = pdr.DataReader(series_id, 'fred', start=(datetime.now() - timedelta(days=365)), api_key=fred_api_key)
        else:
            df = pdr.DataReader(series_id, 'fred', start=(datetime.now() - timedelta(days=365)))
        
        if not df.empty:
            latest_value = float(df.iloc[-1, 0])
            # Save to cache
            _save_cached_data(cache_file, latest_value)
            return latest_value
        return None
    except Exception as e:
        st.warning(f"Could not fetch latest value for {series_id}: {str(e)}")
        # Fallback to offline data
        if can_use_offline_data('fred'):
            st.info("Falling back to offline data")
            try:
                df = pd.read_csv('data/sample_fred_data.csv', index_col=0, parse_dates=True)
                if series_id in df.columns and not df[series_id].empty:
                    return float(df[series_id].iloc[-1])
            except Exception:
                pass
        return None


@st.cache_data(ttl=3600)
def calculate_yoy_change(series_id: str) -> float | None:
    """
    Calculate year-over-year percentage change (12-month change for monthly data).

    Args:
        series_id: FRED series ID

    Returns:
        Year-over-year percentage change as float
    """
    return calculate_percentage_change(series_id, periods=12)


@st.cache_data(ttl=3600)
def calculate_percentage_change(series_id: str, periods: int = 4) -> float | None:
    """
    Calculate percentage change over specified periods.

    Args:
        series_id: FRED series ID
        periods: Number of periods to look back

    Returns:
        Percentage change as float
    """
    # Check offline mode first
    if is_offline_mode():
        try:
            if not can_use_offline_data('fred'):
                st.warning("Offline FRED data not available")
                return None

            df = pd.read_csv('data/sample_fred_data.csv', index_col=0, parse_dates=True)
            if series_id in df.columns and len(df) >= periods + 1:
                latest = df[series_id].iloc[-1]
                previous = df[series_id].iloc[-(periods + 1)]
                return ((latest - previous) / previous) * 100
            return None
        except Exception as e:
            st.error(f"Error loading offline FRED data: {e}")
            return None

    # Try to load from cache
    cache_file = f"{get_cache_dir()}/fred_change_{series_id}_{periods}.pkl"
    cached_data = _load_cached_data(cache_file)
    if cached_data is not None and isinstance(cached_data, (int, float)):
        return float(cached_data)

    # Load from API
    try:
        # Get FRED API key from credentials manager
        creds_manager = get_credentials_manager()
        fred_api_key = creds_manager.get_api_key('fred')
        
        # Use API key if available
        if fred_api_key:
            df = pdr.DataReader(series_id, 'fred', start=(datetime.now() - timedelta(days=730)), api_key=fred_api_key)
        else:
            df = pdr.DataReader(series_id, 'fred', start=(datetime.now() - timedelta(days=730)))
        
        if not df.empty and len(df) >= periods + 1:
            latest = df.iloc[-1, 0]
            previous = df.iloc[-(periods + 1), 0]
            change = ((latest - previous) / previous) * 100
            # Save to cache
            _save_cached_data(cache_file, change)
            return change
        return None
    except Exception as e:
        st.warning(f"Could not calculate change for {series_id}: {str(e)}")
        # Fallback to offline data
        if can_use_offline_data('fred'):
            st.info("Falling back to offline data")
            try:
                df = pd.read_csv('data/sample_fred_data.csv', index_col=0, parse_dates=True)
                if series_id in df.columns and len(df) >= periods + 1:
                    latest = df[series_id].iloc[-1]
                    previous = df[series_id].iloc[-(periods + 1)]
                    return ((latest - previous) / previous) * 100
            except Exception:
                pass
        return None


@st.cache_data(ttl=1800)  # 30 minute cache for options data
def load_options_data(ticker: str, start_date: Optional[str] = None, 
                     end_date: Optional[str] = None) -> pd.DataFrame:
    """
    Load options data for a ticker from DuckDB or fetch from API.
    
    Args:
        ticker: Stock ticker symbol
        start_date: Optional start date (YYYY-MM-DD)
        end_date: Optional end date (YYYY-MM-DD)
        
    Returns:
        DataFrame with options metrics
    """
    # Check offline mode first
    if is_offline_mode():
        st.warning("Options data not available in offline mode")
        return pd.DataFrame()
    
    # Try DuckDB first if available
    if DUCKDB_AVAILABLE:
        try:
            # Import here to avoid circular imports
            from modules.database.queries import get_options_data as db_get_options_data
            db_data = db_get_options_data(ticker, start_date, end_date)
            
            if not db_data.empty:
                return db_data
        except Exception as e:
            st.warning(f"Could not load options from DuckDB: {e}. Falling back to API.")
    
    # Fetch from yfinance API
    try:
        stock = yf.Ticker(ticker)
        options = stock.options
        
        if not options:
            st.warning(f"No options data available for {ticker}")
            return pd.DataFrame()
        
        all_options_data = []
        
        for expiration in options[:5]:  # Limit to first 5 expirations
            try:
                calls = stock.option_chain(expiration).calls
                puts = stock.option_chain(expiration).puts
                
                # Calculate metrics
                calls_volume = calls['volume'].sum() if 'volume' in calls.columns else 0
                puts_volume = puts['volume'].sum() if 'volume' in puts.columns else 0
                calls_oi = calls['openInterest'].sum() if 'openInterest' in calls.columns else 0
                puts_oi = puts['openInterest'].sum() if 'openInterest' in puts.columns else 0
                
                put_call_volume_ratio = puts_volume / calls_volume if calls_volume > 0 else 0
                put_call_oi_ratio = puts_oi / calls_oi if calls_oi > 0 else 0
                
                # Calculate IV metrics (simplified)
                calls_iv = calls['impliedVolatility'].mean() if 'impliedVolatility' in calls.columns else 0
                puts_iv = puts['impliedVolatility'].mean() if 'impliedVolatility' in puts.columns else 0
                
                options_data = {
                    'ticker': ticker,
                    'date': datetime.now().date(),
                    'expiration_date': expiration,
                    'put_volume': puts_volume,
                    'call_volume': calls_volume,
                    'put_open_interest': puts_oi,
                    'call_open_interest': calls_oi,
                    'put_call_volume_ratio': put_call_volume_ratio,
                    'put_call_oi_ratio': put_call_oi_ratio,
                    'total_put_iv': puts_iv,
                    'total_call_iv': calls_iv,
                    'iv_rank': 0,  # Would need more complex calculation
                    'iv_percentile': 0,  # Would need historical comparison
                    'skew': puts_iv - calls_iv if puts_iv and calls_iv else 0
                }
                
                all_options_data.append(options_data)
                
                # Rate limiting
                time.sleep(1)
                
            except Exception as e:
                st.warning(f"Could not load options for {ticker} expiring {expiration}: {e}")
                continue
        
        if all_options_data:
            result_df = pd.DataFrame(all_options_data)
            
            # Save to DuckDB if available
            if DUCKDB_AVAILABLE:
                try:
                    insert_options_data(result_df)
                except Exception as e:
                    st.warning(f"Could not save options data to DuckDB: {e}")
            
            return result_df
        
        return pd.DataFrame()
        
    except Exception as e:
        st.error(f"Error loading options data for {ticker}: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=3600)  # 1 hour cache for technical features
def load_technical_features(ticker: str, start_date: Optional[str] = None,
                           end_date: Optional[str] = None) -> pd.DataFrame:
    """
    Load technical analysis features for a ticker from DuckDB or calculate them.
    
    Args:
        ticker: Stock ticker symbol
        start_date: Optional start date (YYYY-MM-DD)
        end_date: Optional end date (YYYY-MM-DD)
        
    Returns:
        DataFrame with technical indicators
    """
    # Check offline mode first
    if is_offline_mode():
        st.warning("Technical features not available in offline mode")
        return pd.DataFrame()
    
    # Try DuckDB first if available
    if DUCKDB_AVAILABLE:
        try:
            # Import here to avoid circular imports
            from modules.database.queries import get_technical_features as db_get_technical_features
            db_data = db_get_technical_features(ticker, start_date, end_date)
            
            if not db_data.empty:
                return db_data
        except Exception as e:
            st.warning(f"Could not load technical features from DuckDB: {e}. Calculating from OHLCV.")
    
    # Calculate technical features from OHLCV data
    try:
        # Get OHLCV data first
        ohlcv_data = load_yfinance_data({ticker: ticker}, period="2y")
        
        if ticker not in ohlcv_data or ohlcv_data[ticker].empty:
            st.warning(f"No OHLCV data available for {ticker}")
            return pd.DataFrame()
        
        df = ohlcv_data[ticker].copy()
        
        # Import technical analysis library
        try:
            import ta
        except ImportError:
            st.error("ta library not available. Install with: pip install ta")
            return pd.DataFrame()
        
        # Calculate technical indicators
        features = {}
        
        # Momentum indicators
        features['rsi_14'] = ta.momentum.RSIIndicator(df['Close'], window=14).rsi()
        features['rsi_28'] = ta.momentum.RSIIndicator(df['Close'], window=28).rsi()
        features['stoch_k'] = ta.momentum.StochasticOscillator(df['High'], df['Low'], df['Close']).stoch()
        features['stoch_d'] = ta.momentum.StochasticOscillator(df['High'], df['Low'], df['Close']).stoch_signal()
        features['williams_r'] = ta.momentum.WilliamsRIndicator(df['High'], df['Low'], df['Close']).williams_r()
        features['roc_10'] = ta.momentum.ROCIndicator(df['Close'], window=10).roc()
        features['roc_20'] = ta.momentum.ROCIndicator(df['Close'], window=20).roc()
        
        # Trend indicators
        features['sma_20'] = ta.trend.SMAIndicator(df['Close'], window=20).sma_indicator()
        features['sma_50'] = ta.trend.SMAIndicator(df['Close'], window=50).sma_indicator()
        features['sma_200'] = ta.trend.SMAIndicator(df['Close'], window=200).sma_indicator()
        features['ema_12'] = ta.trend.EMAIndicator(df['Close'], window=12).ema_indicator()
        features['ema_26'] = ta.trend.EMAIndicator(df['Close'], window=26).ema_indicator()
        
        macd = ta.trend.MACD(df['Close'])
        features['macd'] = macd.macd()
        features['macd_signal'] = macd.macd_signal()
        features['macd_histogram'] = macd.macd_diff()
        
        features['adx'] = ta.trend.ADXIndicator(df['High'], df['Low'], df['Close']).adx()
        
        # Volatility indicators
        bb = ta.volatility.BollingerBands(df['Close'])
        features['bb_upper'] = bb.bollinger_hband()
        features['bb_middle'] = bb.bollinger_mavg()
        features['bb_lower'] = bb.bollinger_lband()
        features['bb_width'] = (bb.bollinger_hband() - bb.bollinger_lband()) / bb.bollinger_mavg()
        
        features['atr_14'] = ta.volatility.AverageTrueRange(df['High'], df['Low'], df['Close'], window=14).average_true_range()
        
        # Volume indicators
        features['obv'] = ta.volume.OnBalanceVolumeIndicator(df['Close'], df['Volume']).on_balance_volume()
        features['obv_sma'] = ta.trend.SMAIndicator(features['obv'], window=20).sma_indicator()
        features['mfi'] = ta.volume.MFIIndicator(df['High'], df['Low'], df['Close'], df['Volume']).money_flow_index()
        features['ad_line'] = ta.volume.AccDistIndexIndicator(df['High'], df['Low'], df['Close'], df['Volume']).acc_dist_index()
        features['cmf'] = ta.volume.ChaikinMoneyFlowIndicator(df['High'], df['Low'], df['Close'], df['Volume']).chaikin_money_flow()
        features['vwap'] = ta.volume.VolumeWeightedAveragePrice(df['High'], df['Low'], df['Close'], df['Volume']).volume_weighted_average_price()
        
        # Create features DataFrame
        features_df = pd.DataFrame(features)
        features_df['ticker'] = ticker
        features_df['date'] = df.index
        
        # Add custom indicators
        features_df['price_to_sma20'] = df['Close'] / features_df['sma_20']
        features_df['price_to_sma50'] = df['Close'] / features_df['sma_50']
        features_df['price_to_sma200'] = df['Close'] / features_df['sma_200']
        features_df['volume_ratio'] = df['Volume'] / ta.trend.SMAIndicator(df['Volume'], window=20).sma_indicator()
        
        # Reorder columns
        cols = ['ticker', 'date'] + [col for col in features_df.columns if col not in ['ticker', 'date']]
        features_df = features_df[cols]
        
        # Save to DuckDB if available
        if DUCKDB_AVAILABLE:
            try:
                from modules.database.queries import insert_technical_features
                insert_technical_features(features_df)
            except Exception as e:
                st.warning(f"Could not save technical features to DuckDB: {e}")
        
        return features_df
        
    except Exception as e:
        st.error(f"Error calculating technical features for {ticker}: {e}")
        return pd.DataFrame()
