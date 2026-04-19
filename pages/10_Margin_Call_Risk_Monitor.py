"""
Margin Call Risk Monitor Dashboard
Real-time monitoring of margin call risk across stocks and market-wide stress indicators.
"""

import re
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
from modules.features import LeverageMetricsCalculator, MarginCallRiskCalculator
from modules.database import get_db_connection
import logging

# Page configuration
st.set_page_config(
    page_title="Margin Call Risk Monitor",
    page_icon="⚠️",
    layout="wide"
)

st.title("⚠️ Margin Call Risk Monitor")
st.markdown("### Real-time tracking of margin call risk and market stress indicators")

# Initialize components
db = get_db_connection()
leverage_calc = LeverageMetricsCalculator()
risk_calc = MarginCallRiskCalculator()

# Sidebar controls
with st.sidebar:
    st.header("⚙️ Monitor Settings")
    
    # Refresh controls
    if st.button("🔄 Refresh Market Data", use_container_width=True):
        with st.spinner("Fetching latest market data..."):
            try:
                # Fetch VIX data
                vix_data = leverage_calc.fetch_vix_term_structure()
                if vix_data:
                    leverage_calc.store_vix_term_structure(vix_data)
                    st.success("VIX data updated")
                
                # Fetch leveraged ETF data
                etf_tickers = list(leverage_calc.leveraged_etfs.keys())
                etf_data = leverage_calc.fetch_leveraged_etf_data(etf_tickers)
                if etf_data:
                    for ticker, data in etf_data.items():
                        leverage_calc.store_leveraged_etf_data(ticker, data)
                    st.success(f"Updated {len(etf_data)} leveraged ETFs")
                
            except Exception as e:
                st.error(f"Error refreshing data: {str(e)}")
    
    st.divider()
    
    # Risk thresholds
    st.subheader("🎯 Alert Thresholds")
    critical_threshold = st.slider("Critical Risk", 70, 90, 75, help="Score above which risk is critical")
    high_threshold = st.slider("High Risk", 50, 70, 60, help="Score above which risk is high")
    
    st.divider()
    
    # Display options
    st.subheader("📊 Display Options")
    show_historical = st.checkbox("Show Historical Data", value=True)
    days_back = st.slider("Days of History", 7, 90, 30) if show_historical else 30

# Main dashboard layout
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Market Stress Dashboard",
    "🎯 Stock Risk Screener", 
    "📈 Historical Analysis",
    "🔔 Risk Alerts"
])

# Tab 1: Market Stress Dashboard
with tab1:
    st.header("Market-Wide Stress Indicators")
    
    # Get latest VIX data
    vix_result = None
    try:
        vix_query = """
            SELECT * FROM vix_term_structure
            ORDER BY date DESC
            LIMIT 1
        """
        vix_result = db.query(vix_query)
    except Exception as e:
        # Table may not exist yet
        vix_result = pd.DataFrame()
    
    if vix_result is not None and not vix_result.empty:
        latest_vix = vix_result.iloc[0]
        
        # Top metrics row
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            vix_value = latest_vix['vix']
            vix_delta = 0  # Calculate from previous if available
            st.metric(
                "VIX Index",
                f"{vix_value:.2f}",
                delta=f"{vix_delta:+.2f}" if vix_delta != 0 else None,
                delta_color="inverse"
            )
        
        with col2:
            regime = latest_vix['vix_regime']
            regime_colors = {
                'Low': '🟢',
                'Normal': '🟡',
                'Elevated': '🟠',
                'Crisis': '🔴'
            }
            st.metric(
                "Market Regime",
                f"{regime_colors.get(regime, '⚪')} {regime}",
                delta=None
            )
        
        with col3:
            stress_score = latest_vix['stress_score']
            st.metric(
                "Stress Score",
                f"{stress_score:.1f}/100",
                delta=None,
                help="Composite market stress indicator"
            )
        
        with col4:
            vvix_value = latest_vix.get('vvix', 0)
            st.metric(
                "VVIX",
                f"{vvix_value:.2f}",
                delta=None,
                help="Volatility of VIX"
            )
        
        st.divider()
        
        # VIX Historical Chart
        if show_historical:
            st.subheader("VIX Term Structure (30 Days)")
            
            try:
                vix_history_query = f"""
                    SELECT * FROM vix_term_structure
                    WHERE date >= DATE('now', '-{days_back} days')
                    ORDER BY date
                """
                vix_history = db.query(vix_history_query)
            except Exception:
                vix_history = pd.DataFrame()
            
            if not vix_history.empty:
                fig = make_subplots(
                    rows=2, cols=1,
                    subplot_titles=('VIX Level & Regime', 'Stress Score'),
                    row_heights=[0.6, 0.4],
                    vertical_spacing=0.12
                )
                
                # VIX with regime coloring
                colors = vix_history['vix_regime'].map({
                    'Low': 'green',
                    'Normal': 'yellow',
                    'Elevated': 'orange',
                    'Crisis': 'red'
                })
                
                fig.add_trace(
                    go.Scatter(
                        x=vix_history['date'],
                        y=vix_history['vix'],
                        mode='lines+markers',
                        name='VIX',
                        line=dict(color='blue', width=2),
                        marker=dict(color=colors, size=6)
                    ),
                    row=1, col=1
                )
                
                # Regime thresholds
                fig.add_hline(y=15, line_dash="dash", line_color="green", opacity=0.5, row=1, col=1)
                fig.add_hline(y=20, line_dash="dash", line_color="orange", opacity=0.5, row=1, col=1)
                fig.add_hline(y=30, line_dash="dash", line_color="red", opacity=0.5, row=1, col=1)
                
                # Stress score
                fig.add_trace(
                    go.Scatter(
                        x=vix_history['date'],
                        y=vix_history['stress_score'],
                        mode='lines',
                        name='Stress Score',
                        fill='tozeroy',
                        line=dict(color='purple', width=2)
                    ),
                    row=2, col=1
                )
                
                fig.update_xaxes(title_text="Date", row=2, col=1)
                fig.update_yaxes(title_text="VIX Level", row=1, col=1)
                fig.update_yaxes(title_text="Score (0-100)", row=2, col=1)
                
                fig.update_layout(height=600, showlegend=True)
                st.plotly_chart(fig, use_container_width=True)
    
    else:
        st.warning("⚠️ No VIX data available. Click 'Refresh Market Data' to fetch latest.")
    
    st.divider()
    
    # Leveraged ETF Stress Monitor
    st.subheader("Leveraged ETF Stress Indicators")
    st.markdown("*3x leveraged ETFs often signal extreme market sentiment*")
    
    try:
        etf_query = """
            SELECT * FROM leveraged_etf_data
            WHERE date = (SELECT MAX(date) FROM leveraged_etf_data)
            ORDER BY stress_indicator DESC
        """
        etf_data = db.query(etf_query)
    except Exception:
        etf_data = pd.DataFrame()
    
    if not etf_data.empty:
        # Create ETF stress gauge
        col1, col2 = st.columns([2, 1])
        
        with col1:
            # Bar chart of ETF stress
            fig = go.Figure()
            
            colors_map = etf_data['stress_indicator'].apply(
                lambda x: 'red' if x > 70 else 'orange' if x > 50 else 'yellow' if x > 30 else 'green'
            )
            
            fig.add_trace(go.Bar(
                x=etf_data['ticker'],
                y=etf_data['stress_indicator'],
                marker_color=colors_map,
                text=etf_data['stress_indicator'].round(1),
                textposition='outside'
            ))
            
            fig.update_layout(
                title="Leveraged ETF Stress Levels",
                xaxis_title="ETF Ticker",
                yaxis_title="Stress Indicator (0-100)",
                height=400,
                showlegend=False
            )
            
            fig.add_hline(y=70, line_dash="dash", line_color="red", annotation_text="Critical")
            fig.add_hline(y=50, line_dash="dash", line_color="orange", annotation_text="High")
            
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.markdown("**Top Stressed ETFs**")
            top_stress = etf_data.nlargest(5, 'stress_indicator')[['ticker', 'stress_indicator', 'volume_ratio']]
            for _, row in top_stress.iterrows():
                stress_emoji = "🔴" if row['stress_indicator'] > 70 else "🟠" if row['stress_indicator'] > 50 else "🟡"
                st.markdown(f"{stress_emoji} **{row['ticker']}**: {row['stress_indicator']:.1f} (Vol: {row['volume_ratio']:.1f}x)")
    else:
        st.info("No leveraged ETF data available. Refresh to fetch latest.")

# Tab 2: Stock Risk Screener
with tab2:
    st.header("Stock Margin Call Risk Screener")
    
    # Get all stocks with margin risk scores
    try:
        risk_query = """
            SELECT 
                ticker,
                date,
                composite_risk_score,
                risk_level,
                leverage_score,
                volatility_score,
                options_score,
                liquidity_score,
                short_interest_pct,
                put_call_ratio,
                vix_regime
            FROM margin_call_risk
            WHERE date = (SELECT MAX(date) FROM margin_call_risk)
            ORDER BY composite_risk_score DESC
        """
        risk_data = db.query(risk_query)
    except Exception:
        risk_data = pd.DataFrame()
    
    if not risk_data.empty:
        # Filter controls
        col1, col2, col3 = st.columns(3)
        
        with col1:
            risk_filter = st.multiselect(
                "Filter by Risk Level",
                options=['Critical', 'High', 'Moderate', 'Low', 'Minimal'],
                default=['Critical', 'High']
            )
        
        with col2:
            min_score = st.slider("Minimum Risk Score", 0, 100, high_threshold)
        
        with col3:
            sort_by = st.selectbox(
                "Sort By",
                options=['Composite Score', 'Leverage', 'Volatility', 'Options', 'Liquidity']
            )
        
        # Apply filters
        filtered_data = risk_data[
            (risk_data['risk_level'].isin(risk_filter)) &
            (risk_data['composite_risk_score'] >= min_score)
        ].copy()
        
        # Sort
        sort_map = {
            'Composite Score': 'composite_risk_score',
            'Leverage': 'leverage_score',
            'Volatility': 'volatility_score',
            'Options': 'options_score',
            'Liquidity': 'liquidity_score'
        }
        filtered_data = filtered_data.sort_values(sort_map[sort_by], ascending=False)
        
        st.markdown(f"**Found {len(filtered_data)} stocks matching criteria**")
        
        # Display table
        display_data = filtered_data[[
            'ticker', 'composite_risk_score', 'risk_level',
            'leverage_score', 'volatility_score', 'options_score', 'liquidity_score',
            'short_interest_pct', 'put_call_ratio'
        ]].copy()
        
        # Format columns
        for col in ['composite_risk_score', 'leverage_score', 'volatility_score', 'options_score', 'liquidity_score']:
            display_data[col] = display_data[col].round(1)
        
        display_data['short_interest_pct'] = display_data['short_interest_pct'].round(2)
        display_data['put_call_ratio'] = display_data['put_call_ratio'].round(2)
        
        # Color-code risk levels
        def highlight_risk(row):
            if row['risk_level'] == 'Critical':
                return ['background-color: #ffcccc'] * len(row)
            elif row['risk_level'] == 'High':
                return ['background-color: #ffe6cc'] * len(row)
            elif row['risk_level'] == 'Moderate':
                return ['background-color: #ffffcc'] * len(row)
            return [''] * len(row)
        
        styled_data = display_data.style.apply(highlight_risk, axis=1)
        st.dataframe(styled_data, use_container_width=True, height=400)
        
        # Component breakdown for selected stock
        st.divider()
        st.subheader("Risk Component Analysis")
        
        selected_ticker = st.selectbox(
            "Select Stock for Detailed Analysis",
            options=filtered_data['ticker'].tolist()
        )
        
        if selected_ticker:
            stock_data = filtered_data[filtered_data['ticker'] == selected_ticker].iloc[0]
            
            col1, col2 = st.columns([1, 2])
            
            with col1:
                # Risk gauge
                fig = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=stock_data['composite_risk_score'],
                    domain={'x': [0, 1], 'y': [0, 1]},
                    title={'text': f"{selected_ticker} Risk Score"},
                    delta={'reference': 50},
                    gauge={
                        'axis': {'range': [None, 100]},
                        'bar': {'color': "darkblue"},
                        'steps': [
                            {'range': [0, 25], 'color': "lightgreen"},
                            {'range': [25, 40], 'color': "yellow"},
                            {'range': [40, 60], 'color': "orange"},
                            {'range': [60, 75], 'color': "darkorange"},
                            {'range': [75, 100], 'color': "red"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': critical_threshold
                        }
                    }
                ))
                
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Component breakdown
                components = {
                    'Leverage (30%)': stock_data['leverage_score'],
                    'Volatility (25%)': stock_data['volatility_score'],
                    'Options (25%)': stock_data['options_score'],
                    'Liquidity (20%)': stock_data['liquidity_score']
                }
                
                fig = go.Figure()
                
                fig.add_trace(go.Bar(
                    x=list(components.keys()),
                    y=list(components.values()),
                    marker_color=['#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4'],
                    text=[f"{v:.1f}" for v in components.values()],
                    textposition='outside'
                ))
                
                fig.update_layout(
                    title=f"{selected_ticker} Risk Components",
                    yaxis_title="Score (0-100)",
                    height=300,
                    showlegend=False
                )
                
                fig.add_hline(y=75, line_dash="dash", line_color="red", annotation_text="Critical")
                fig.add_hline(y=60, line_dash="dash", line_color="orange", annotation_text="High")
                
                st.plotly_chart(fig, use_container_width=True)
            
            # Detailed metrics
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Short Interest", f"{stock_data['short_interest_pct']:.1f}%")
            with col2:
                st.metric("Put/Call Ratio", f"{stock_data['put_call_ratio']:.2f}")
            with col3:
                st.metric("Risk Level", stock_data['risk_level'])
            with col4:
                st.metric("VIX Regime", stock_data['vix_regime'])
    
    else:
        st.warning("⚠️ No margin risk data available. Run margin risk calculation for stocks first.")
        
        with st.expander("📝 How to Calculate Margin Risk"):
            st.markdown("""
            **To populate this dashboard:**
            
            1. Use the `MarginCallRiskCalculator` to calculate risk for your stocks:
            ```python
            from modules.features import MarginCallRiskCalculator
            
            calc = MarginCallRiskCalculator()
            
            # Calculate for a single stock
            risk_data = calc.calculate_and_store('AAPL')
            
            # Or batch process multiple stocks
            tickers = ['AAPL', 'TSLA', 'NVDA', 'AMD', 'MSFT']
            for ticker in tickers:
                calc.calculate_and_store(ticker)
            ```
            
            2. Refresh this dashboard to see the results.
            """)

# Tab 3: Historical Analysis
with tab3:
    st.header("Historical Margin Risk Analysis")
    
    # Ticker selection for historical view
    ticker_for_history = st.text_input(
        "Enter Ticker Symbol",
        value="AAPL",
        help="Enter a stock ticker to view historical margin risk"
    )
    
    if ticker_for_history:
        ticker_for_history = ticker_for_history.upper().strip()
        if not re.match(r'^[A-Z]{1,5}(\.[A-Z]{1,2})?$', ticker_for_history):
            st.error("Invalid ticker symbol. Use 1–5 uppercase letters (e.g. AAPL, BRK.B).")
            ticker_for_history = None

    if ticker_for_history:
        try:
            history_query = f"""
                SELECT * FROM margin_call_risk
                WHERE ticker = ?
                AND date >= DATE('now', '-{days_back} days')
                ORDER BY date
            """
            history_data = db.query(history_query, (ticker_for_history,))
        except Exception:
            history_data = pd.DataFrame()
        
        if not history_data.empty:
            # Multi-line chart of all components
            fig = make_subplots(
                rows=2, cols=1,
                subplot_titles=(
                    f'{ticker_for_history} Risk Components Over Time',
                    f'{ticker_for_history} Composite Risk Score'
                ),
                row_heights=[0.6, 0.4],
                vertical_spacing=0.12
            )
            
            # Component scores
            fig.add_trace(
                go.Scatter(x=history_data['date'], y=history_data['leverage_score'],
                          mode='lines', name='Leverage', line=dict(color='red', width=2)),
                row=1, col=1
            )
            fig.add_trace(
                go.Scatter(x=history_data['date'], y=history_data['volatility_score'],
                          mode='lines', name='Volatility', line=dict(color='orange', width=2)),
                row=1, col=1
            )
            fig.add_trace(
                go.Scatter(x=history_data['date'], y=history_data['options_score'],
                          mode='lines', name='Options', line=dict(color='purple', width=2)),
                row=1, col=1
            )
            fig.add_trace(
                go.Scatter(x=history_data['date'], y=history_data['liquidity_score'],
                          mode='lines', name='Liquidity', line=dict(color='blue', width=2)),
                row=1, col=1
            )
            
            # Composite score with risk level shading
            fig.add_trace(
                go.Scatter(
                    x=history_data['date'],
                    y=history_data['composite_risk_score'],
                    mode='lines+markers',
                    name='Composite Risk',
                    line=dict(color='black', width=3),
                    fill='tozeroy'
                ),
                row=2, col=1
            )
            
            # Risk threshold lines
            fig.add_hline(y=75, line_dash="dash", line_color="red", annotation_text="Critical", row=2, col=1)
            fig.add_hline(y=60, line_dash="dash", line_color="orange", annotation_text="High", row=2, col=1)
            fig.add_hline(y=40, line_dash="dash", line_color="yellow", annotation_text="Moderate", row=2, col=1)
            
            fig.update_xaxes(title_text="Date", row=2, col=1)
            fig.update_yaxes(title_text="Score (0-100)", row=1, col=1)
            fig.update_yaxes(title_text="Composite Score", row=2, col=1)
            
            fig.update_layout(height=700, showlegend=True)
            st.plotly_chart(fig, use_container_width=True)
            
            # Statistics
            st.subheader("Risk Statistics")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                avg_risk = history_data['composite_risk_score'].mean()
                st.metric("Average Risk", f"{avg_risk:.1f}")
            
            with col2:
                max_risk = history_data['composite_risk_score'].max()
                st.metric("Maximum Risk", f"{max_risk:.1f}")
            
            with col3:
                days_high = (history_data['composite_risk_score'] > 60).sum()
                st.metric("Days at High Risk", f"{days_high}")
            
            with col4:
                current_trend = "Rising" if history_data['composite_risk_score'].iloc[-1] > history_data['composite_risk_score'].iloc[-5] else "Falling"
                st.metric("Risk Trend", current_trend)
        
        else:
            st.info(f"No historical data found for {ticker_for_history.upper()}")

# Tab 4: Risk Alerts
with tab4:
    st.header("Risk Alert Configuration")
    
    st.markdown("""
    Configure automated alerts for margin call risk events.
    Alerts trigger when:
    - Stock crosses critical/high risk thresholds
    - VIX regime changes (e.g., Normal → Elevated)
    - Leveraged ETF stress spikes
    """)
    
    # Alert settings
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Stock Risk Alerts")
        
        enable_stock_alerts = st.checkbox("Enable Stock Alerts", value=True)
        
        if enable_stock_alerts:
            alert_tickers = st.text_area(
                "Monitor These Tickers (comma-separated)",
                value="AAPL, TSLA, NVDA, AMD",
                help="Enter tickers to monitor for risk changes"
            )
            
            alert_critical = st.number_input("Critical Risk Threshold", 70, 95, 75)
            alert_high = st.number_input("High Risk Threshold", 50, 70, 60)
            
            if st.button("Save Stock Alert Settings"):
                st.success("✅ Stock alert settings saved!")
    
    with col2:
        st.subheader("Market Stress Alerts")
        
        enable_market_alerts = st.checkbox("Enable Market Alerts", value=True)
        
        if enable_market_alerts:
            alert_vix_crisis = st.number_input("VIX Crisis Level", 25, 40, 30)
            alert_vix_elevated = st.number_input("VIX Elevated Level", 15, 25, 20)
            
            alert_etf_stress = st.number_input("ETF Stress Threshold", 50, 90, 70)
            
            if st.button("Save Market Alert Settings"):
                st.success("✅ Market alert settings saved!")
    
    st.divider()
    
    # Recent alerts (simulated)
    st.subheader("Recent Alerts")
    
    # Query for stocks that crossed thresholds recently
    try:
        recent_alerts_query = f"""
            SELECT 
                ticker,
                date,
                composite_risk_score,
                risk_level,
                vix_regime
            FROM margin_call_risk
            WHERE composite_risk_score > {critical_threshold}
            AND date >= DATE('now', '-7 days')
            ORDER BY date DESC, composite_risk_score DESC
            LIMIT 10
        """
        recent_alerts = db.query(recent_alerts_query)
    except Exception:
        recent_alerts = pd.DataFrame()
    
    if not recent_alerts.empty:
        for _, alert in recent_alerts.iterrows():
            alert_emoji = "🔴" if alert['composite_risk_score'] > 75 else "🟠"
            st.warning(
                f"{alert_emoji} **{alert['ticker']}** reached {alert['risk_level']} risk "
                f"({alert['composite_risk_score']:.1f}) on {alert['date']} "
                f"| VIX Regime: {alert['vix_regime']}"
            )
    else:
        st.info("No recent critical risk alerts")

# Footer
st.divider()
st.markdown("""
**About Margin Call Risk Monitor**

This dashboard tracks four key risk components:
- **Leverage (30%)**: Short interest, days to cover, margin exposure
- **Volatility (25%)**: Realized volatility, VIX regime, Bollinger Band width
- **Options (25%)**: Put/call ratio, IV rank, put skew
- **Liquidity (20%)**: Volume trends, bid-ask spreads

Risk Levels: Minimal (0-25) | Low (25-40) | Moderate (40-60) | High (60-75) | Critical (75-100)

*Data updates: VIX (daily), Leveraged ETFs (daily), Short Interest (bi-weekly)*
""")
