"""
Secure credentials management for API keys and authentication tokens.
Provides encrypted storage and retrieval of sensitive credentials.
Falls back to st.secrets when running on Streamlit Community Cloud.
"""

import os
import json
from typing import Optional, Dict
from cryptography.fernet import Fernet
from pathlib import Path

# Streamlit secrets key names map service names to st.secrets keys
_STREAMLIT_SECRETS_KEYS = {
    'fred': 'FRED_API_KEY',
    'yahoo_finance': 'YAHOO_FINANCE_API_KEY',
    'alpha_vantage': 'ALPHA_VANTAGE_API_KEY',
    'quandl': 'QUANDL_API_KEY',
    'world_bank': 'WORLD_BANK_API_KEY',
}


def _get_from_streamlit_secrets(service: str) -> Optional[str]:
    """Return API key from st.secrets if available, else None."""
    try:
        import streamlit as st
        key_name = _STREAMLIT_SECRETS_KEYS.get(service, service.upper() + '_API_KEY')
        return st.secrets.get(key_name)
    except Exception:
        return None


class CredentialsManager:
    """Manage API keys and credentials securely"""

    # Key file lives one level above the credentials data directory so that
    # a directory-listing leak of data/credentials/ does not expose both the
    # key and the ciphertext at once.
    _KEY_SUBDIR = '.credentials_key'

    def __init__(self, credentials_dir: str = 'data/credentials'):
        """
        Initialize credentials manager.

        The encryption key is resolved in priority order:
          1. CREDENTIALS_KEY environment variable (base64-encoded Fernet key)
          2. Key file at <parent_of_credentials_dir>/.credentials_key
          3. Legacy key file at <credentials_dir>/.key  (backward-compat)

        Args:
            credentials_dir: Directory to store encrypted credentials
        """
        self.credentials_dir = Path(credentials_dir)
        self.credentials_dir.mkdir(parents=True, exist_ok=True)

        self._key_file = self.credentials_dir.parent / self._KEY_SUBDIR
        # Expose for inspection/testing (legacy path kept for compat check)
        self.key_file = self._key_file

        self.cipher = self._init_encryption()

        # Credentials file
        self.creds_file = self.credentials_dir / 'credentials.enc'

    def _init_encryption(self) -> Fernet:
        """Initialize encryption cipher with key, preferring env var over file."""
        env_key = os.environ.get('CREDENTIALS_KEY', '').strip()
        if env_key:
            return Fernet(env_key.encode())

        # Out-of-band key file (parent directory)
        if self._key_file.exists():
            with open(self._key_file, 'rb') as f:
                key = f.read()
            return Fernet(key)

        # Backward-compat: migrate legacy key from inside credentials dir
        legacy_key_file = self.credentials_dir / '.key'
        if legacy_key_file.exists():
            with open(legacy_key_file, 'rb') as f:
                key = f.read()
            # Move key out of the data directory
            with open(self._key_file, 'wb') as f:
                f.write(key)
            os.chmod(self._key_file, 0o600)
            legacy_key_file.unlink()
            return Fernet(key)

        # Generate a new key in the out-of-band location
        key = Fernet.generate_key()
        with open(self._key_file, 'wb') as f:
            f.write(key)
        os.chmod(self._key_file, 0o600)
        return Fernet(key)
    
    def _load_credentials(self) -> Dict[str, str]:
        """Load and decrypt all credentials"""
        if not self.creds_file.exists():
            return {}
        
        try:
            with open(self.creds_file, 'rb') as f:
                encrypted_data = f.read()
            
            decrypted_data = self.cipher.decrypt(encrypted_data)
            return json.loads(decrypted_data.decode())
        except Exception as e:
            print(f"Warning: Could not load credentials: {e}")
            return {}
    
    def _save_credentials(self, credentials: Dict[str, str]):
        """Encrypt and save all credentials"""
        try:
            json_data = json.dumps(credentials).encode()
            encrypted_data = self.cipher.encrypt(json_data)
            
            with open(self.creds_file, 'wb') as f:
                f.write(encrypted_data)
            
            # Secure the credentials file
            os.chmod(self.creds_file, 0o600)
        except Exception as e:
            print(f"Error saving credentials: {e}")
    
    def set_api_key(self, service: str, api_key: str):
        """
        Store an API key securely.
        
        Args:
            service: Name of the service (e.g., 'fred', 'yahoo_finance')
            api_key: The API key to store
        """
        credentials = self._load_credentials()
        credentials[service] = api_key
        self._save_credentials(credentials)
    
    def get_api_key(self, service: str) -> Optional[str]:
        """
        Retrieve an API key.

        Args:
            service: Name of the service

        Returns:
            API key if found, None otherwise
        """
        credentials = self._load_credentials()
        return credentials.get(service) or _get_from_streamlit_secrets(service)
    
    def delete_api_key(self, service: str) -> bool:
        """
        Delete an API key.
        
        Args:
            service: Name of the service
            
        Returns:
            True if deleted, False if not found
        """
        credentials = self._load_credentials()
        if service in credentials:
            del credentials[service]
            self._save_credentials(credentials)
            return True
        return False
    
    def list_services(self) -> list:
        """Get list of services with stored credentials"""
        credentials = self._load_credentials()
        return list(credentials.keys())
    
    def has_api_key(self, service: str) -> bool:
        """Check if API key exists for service"""
        return bool(self.get_api_key(service))


# Global instance for easy access
_credentials_manager = None

def get_credentials_manager() -> CredentialsManager:
    """Get global credentials manager instance"""
    global _credentials_manager
    if _credentials_manager is None:
        _credentials_manager = CredentialsManager()
    return _credentials_manager
