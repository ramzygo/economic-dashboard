#!/usr/bin/env python3
"""
Quick Start: Initialize and test API key management
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

def main():
    print("=" * 60)
    print("🚀 Economic Dashboard - API Key Management Setup")
    print("=" * 60)
    
    # Step 1: Initialize credentials
    print("\n📝 Step 1: Setting up credentials manager...")
    try:
        from modules.auth.credentials_manager import get_credentials_manager
        creds_manager = get_credentials_manager()
        print("✅ Credentials manager initialized")
    except Exception as e:
        print(f"❌ Error initializing credentials manager: {e}")
        return 1
    
    # Step 2: Store FRED API key
    print("\n🔑 Step 2: Storing FRED API key...")
    try:
        fred_key = os.environ.get('FRED_API_KEY') or input("Enter your FRED API key: ").strip()
        if not fred_key:
            print("❌ No FRED API key provided. Get one at https://fred.stlouisfed.org/docs/api/api_key.html")
            return 1
        creds_manager.set_api_key('fred', fred_key)
        print("✅ FRED API key stored securely")
    except Exception as e:
        print(f"❌ Error storing API key: {e}")
        return 1

    # Step 3: Verify storage
    print("\n✓ Step 3: Verifying API key storage...")
    try:
        retrieved_key = creds_manager.get_api_key('fred')
        if retrieved_key == fred_key:
            print("✅ API key verified successfully")
            print(f"   Key preview: {retrieved_key[:10]}...{retrieved_key[-10:]}")
        else:
            print("❌ API key verification failed")
            return 1
    except Exception as e:
        print(f"❌ Error verifying API key: {e}")
        return 1
    
    # Step 4: List configured services
    print("\n📋 Step 4: Configured services:")
    services = creds_manager.list_services()
    for service in services:
        print(f"   ✓ {service.upper()}")
    
    # Step 5: Test data loader integration
    print("\n🔗 Step 5: Testing data loader integration...")
    try:
        from modules.data_loader import load_fred_data
        print("✅ Data loader module imported successfully")
        print("   FRED API key will be automatically used for data requests")
    except Exception as e:
        print(f"❌ Error importing data loader: {e}")
        return 1
    
    # Summary
    print("\n" + "=" * 60)
    print("🎉 Setup Complete!")
    print("=" * 60)
    print("\n✅ What's been configured:")
    print("   • Secure credentials storage initialized")
    print("   • FRED API key stored and encrypted")
    print("   • Data loader updated to use API key")
    print("   • Higher rate limits now available")
    
    print("\n📊 Next steps:")
    print("   1. Run the dashboard: streamlit run app.py")
    print("   2. Check API key status in the sidebar")
    print("   3. Visit 'API Key Management' page to add more keys")
    print("   4. Enjoy faster, more reliable data access!")
    
    print("\n💡 Pro tips:")
    print("   • Add more API keys via the UI (pages/3_API_Key_Management.py)")
    print("   • Credentials are stored in: data/credentials/ (encrypted)")
    print("   • Never commit the credentials directory to git")
    
    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
