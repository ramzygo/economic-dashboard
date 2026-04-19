"""
Financial Health Scorer Dashboard
Analyze company financial health using Piotroski F-Score and Altman Z-Score
"""

import re
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# Import financial health scorer
try:
    from modules.features import FinancialHealthScorer
    from modules.sec_data_loader import lookup_cik
    SCORER_AVAILABLE = True
except ImportError as e:
    SCORER_AVAILABLE = False
    SCORER_ERROR = str(e)

# Page configuration
st.set_page_config(
    page_title="Financial Health Scorer",
    page_icon="💊",
    layout="wide"
)

st.title("💊 Financial Health Scorer")
st.markdown("### Fundamental analysis using Piotroski F-Score and Altman Z-Score")

if not SCORER_AVAILABLE:
    st.error(f"❌ Financial Health Scorer not available: {SCORER_ERROR}")
    st.stop()

# Initialize scorer
scorer = FinancialHealthScorer()

# Sidebar controls
with st.sidebar:
    st.header("🎯 Analysis Settings")
    
    ticker_input = st.text_input(
        "Enter Ticker Symbol",
        value="AAPL",
        help="Enter a stock ticker (e.g., AAPL, MSFT, GOOGL)"
    ).upper().strip()
    
    st.divider()
    
    st.subheader("📊 Score Explanations")
    
    with st.expander("🔢 Piotroski F-Score (0-9)"):
        st.markdown("""
        **Measures fundamental strength across 3 categories:**
        
        **Profitability (4 points):**
        - Positive ROA
        - Positive operating cash flow
        - Increasing ROA
        - Quality of earnings (CFO > NI)
        
        **Leverage (3 points):**
        - Decreasing debt ratio
        - Increasing current ratio
        - No new shares issued
        
        **Efficiency (2 points):**
        - Increasing gross margin
        - Increasing asset turnover
        
        **Interpretation:**
        - **7-9**: Strong fundamentals
        - **5-6**: Good fundamentals
        - **3-4**: Average
        - **0-2**: Weak fundamentals
        """)
    
    with st.expander("📉 Altman Z-Score"):
        st.markdown("""
        **Predicts bankruptcy risk using 5 ratios:**
        
        Z = 1.2×(WC/TA) + 1.4×(RE/TA) + 
            3.3×(EBIT/TA) + 0.6×(MVE/TL) + 
            1.0×(Sales/TA)
        
        **Interpretation:**
        - **Z > 2.99**: Safe Zone (low risk)
        - **1.81-2.99**: Grey Zone (moderate risk)
        - **Z < 1.81**: Distress Zone (high risk)
        
        **Components:**
        - WC = Working Capital
        - TA = Total Assets
        - RE = Retained Earnings
        - EBIT = Earnings Before Interest & Tax
        - MVE = Market Value of Equity
        - TL = Total Liabilities
        """)

# Main content
if ticker_input:
    if not re.match(r'^[A-Z]{1,5}(\.[A-Z]{1,2})?$', ticker_input):
        st.error("Invalid ticker symbol. Use 1–5 uppercase letters (e.g. AAPL, BRK.B).")
        st.stop()

    st.header(f"Financial Health Analysis: {ticker_input}")
    
    # CIK lookup
    with st.spinner(f"Looking up {ticker_input}..."):
        cik = lookup_cik(ticker_input)
        
        if not cik:
            st.error(f"❌ Could not find SEC CIK for ticker {ticker_input}. Please verify the ticker symbol.")
            st.stop()
        
        st.success(f"✅ Found CIK: {cik}")
    
    # Create tabs for different analyses
    tab1, tab2, tab3 = st.tabs([
        "📊 Composite Score",
        "🔢 Piotroski F-Score",
        "📉 Altman Z-Score"
    ])
    
    # === TAB 1: COMPOSITE SCORE ===
    with tab1:
        st.subheader("Comprehensive Financial Health Score")
        
        with st.spinner("Calculating composite health score..."):
            composite = scorer.calculate_composite_health_score(ticker_input, cik)
        
        if 'error' in composite:
            st.error(f"❌ Error: {composite['error']}")
        else:
            # Display overall score
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                # Gauge chart for composite score
                fig = go.Figure(go.Indicator(
                    mode="gauge+number+delta",
                    value=composite['composite_score'],
                    domain={'x': [0, 1], 'y': [0, 1]},
                    title={'text': f"{ticker_input} Financial Health", 'font': {'size': 24}},
                    delta={'reference': 50, 'increasing': {'color': "green"}},
                    gauge={
                        'axis': {'range': [None, 100], 'tickwidth': 1},
                        'bar': {'color': "darkblue"},
                        'bgcolor': "white",
                        'borderwidth': 2,
                        'bordercolor': "gray",
                        'steps': [
                            {'range': [0, 20], 'color': '#ffcccc'},
                            {'range': [20, 40], 'color': '#ffe6cc'},
                            {'range': [40, 60], 'color': '#ffffcc'},
                            {'range': [60, 80], 'color': '#ccffcc'},
                            {'range': [80, 100], 'color': '#99ff99'}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': 70
                        }
                    }
                ))
                
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.metric(
                    "Health Rating",
                    composite['health_rating'],
                    help="Overall financial health classification"
                )
                st.metric(
                    "Composite Score",
                    f"{composite['composite_score']:.1f}/100"
                )
            
            with col3:
                st.metric(
                    "Piotroski F-Score",
                    f"{composite['components']['piotroski'].get('f_score', 'N/A')}/9"
                )
                st.metric(
                    "Altman Z-Score",
                    f"{composite['components']['altman'].get('z_score', 'N/A'):.2f}"
                )
            
            st.divider()
            
            # Score breakdown
            st.subheader("Score Component Breakdown")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Normalized scores bar chart
                norm_scores = composite.get('normalized_scores', {})
                
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=['Piotroski\n(40% weight)', 'Altman Z\n(30% weight)'],
                    y=[norm_scores.get('piotroski', 0), norm_scores.get('altman', 0)],
                    marker_color=['#4CAF50', '#2196F3'],
                    text=[f"{norm_scores.get('piotroski', 0):.1f}", f"{norm_scores.get('altman', 0):.1f}"],
                    textposition='outside'
                ))
                
                fig.update_layout(
                    title="Normalized Component Scores (0-100)",
                    yaxis_title="Score",
                    yaxis=dict(range=[0, 100]),
                    showlegend=False,
                    height=350
                )
                
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Piotroski subscore breakdown
                piotroski_data = composite['components']['piotroski']
                
                subscores = pd.DataFrame({
                    'Category': ['Profitability', 'Leverage', 'Efficiency'],
                    'Score': [
                        piotroski_data.get('profitability_score', 0),
                        piotroski_data.get('leverage_score', 0),
                        piotroski_data.get('efficiency_score', 0)
                    ],
                    'Max': [4, 3, 2]
                })
                
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    name='Score',
                    x=subscores['Category'],
                    y=subscores['Score'],
                    marker_color='#FF9800'
                ))
                fig.add_trace(go.Bar(
                    name='Remaining',
                    x=subscores['Category'],
                    y=subscores['Max'] - subscores['Score'],
                    marker_color='lightgray'
                ))
                
                fig.update_layout(
                    title="Piotroski Subscore Breakdown",
                    barmode='stack',
                    yaxis_title="Points",
                    height=350
                )
                
                st.plotly_chart(fig, use_container_width=True)
    
    # === TAB 2: PIOTROSKI F-SCORE ===
    with tab2:
        st.subheader("Piotroski F-Score Detailed Analysis")
        
        with st.spinner("Calculating Piotroski F-Score..."):
            piotroski = scorer.calculate_piotroski_score(ticker_input, cik)
        
        if 'error' in piotroski:
            st.error(f"❌ Error: {piotroski['error']}")
        else:
            # Overall score
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("F-Score", f"{piotroski['f_score']}/9")
            with col2:
                st.metric("Classification", piotroski['classification'])
            with col3:
                st.metric("Profitability", f"{piotroski['profitability_score']}/4")
            with col4:
                st.metric("Fiscal Year", piotroski.get('as_of_date', 'N/A'))
            
            st.divider()
            
            # Detailed breakdown
            st.subheader("Criterion-by-Criterion Analysis")
            
            breakdown = piotroski.get('breakdown', {})
            
            # Create a DataFrame for display
            criteria_data = []
            
            # Profitability
            st.markdown("#### 💰 Profitability (4 points)")
            prof_criteria = [
                ('positive_roa', 'Positive ROA', 'ROA > 0'),
                ('positive_cfo', 'Positive Operating Cash Flow', 'CFO > 0'),
                ('increasing_roa', 'Increasing ROA vs Prior Year', 'ROA trending up'),
                ('quality_earnings', 'Quality of Earnings', 'CFO > Net Income')
            ]
            
            for key, name, description in prof_criteria:
                if key in breakdown:
                    data = breakdown[key]
                    criteria_data.append({
                        'Criterion': name,
                        'Points': data['points'],
                        'Status': '✅ Pass' if data['points'] == 1 else '❌ Fail',
                        'Details': description
                    })
            
            # Leverage
            st.markdown("#### 💎 Leverage/Liquidity (3 points)")
            lev_criteria = [
                ('decreasing_leverage', 'Decreasing Debt Ratio', 'LT Debt/Assets down'),
                ('increasing_current_ratio', 'Increasing Current Ratio', 'Current Ratio up'),
                ('no_new_shares', 'No Share Dilution', 'Shares outstanding same/down')
            ]
            
            for key, name, description in lev_criteria:
                if key in breakdown:
                    data = breakdown[key]
                    criteria_data.append({
                        'Criterion': name,
                        'Points': data['points'],
                        'Status': '✅ Pass' if data['points'] == 1 else '❌ Fail',
                        'Details': description
                    })
            
            # Efficiency
            st.markdown("#### ⚡ Operating Efficiency (2 points)")
            eff_criteria = [
                ('increasing_margin', 'Increasing Gross Margin', 'Gross Margin trending up'),
                ('increasing_turnover', 'Increasing Asset Turnover', 'Sales/Assets up')
            ]
            
            for key, name, description in eff_criteria:
                if key in breakdown:
                    data = breakdown[key]
                    criteria_data.append({
                        'Criterion': name,
                        'Points': data['points'],
                        'Status': '✅ Pass' if data['points'] == 1 else '❌ Fail',
                        'Details': description
                    })
            
            # Display table
            df = pd.DataFrame(criteria_data)
            
            # Style the dataframe
            def highlight_status(row):
                if '✅' in row['Status']:
                    return ['background-color: #ccffcc'] * len(row)
                else:
                    return ['background-color: #ffcccc'] * len(row)
            
            styled_df = df.style.apply(highlight_status, axis=1)
            st.dataframe(styled_df, use_container_width=True, hide_index=True)
    
    # === TAB 3: ALTMAN Z-SCORE ===
    with tab3:
        st.subheader("Altman Z-Score Bankruptcy Risk Analysis")
        
        with st.spinner("Calculating Altman Z-Score..."):
            altman = scorer.calculate_altman_z_score(ticker_input, cik)
        
        if 'error' in altman:
            st.error(f"❌ Error: {altman['error']}")
        else:
            # Overall score and risk
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Z-Score", f"{altman['z_score']:.2f}")
            with col2:
                risk_color = {
                    'Safe Zone': '🟢',
                    'Grey Zone': '🟡',
                    'Distress Zone': '🔴'
                }
                st.metric(
                    "Risk Zone",
                    f"{risk_color.get(altman['risk_zone'], '⚪')} {altman['risk_zone']}"
                )
            with col3:
                st.metric("Risk Level", altman['risk_level'])
            with col4:
                st.metric(
                    "Distance to Distress",
                    f"{altman['interpretation']['distance_to_distress']:.2f}"
                )
            
            st.divider()
            
            # Z-Score visualization
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Z-Score gauge with zones
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=altman['z_score'],
                    domain={'x': [0, 1], 'y': [0, 1]},
                    title={'text': "Z-Score Risk Meter"},
                    gauge={
                        'axis': {'range': [0, 6], 'tickwidth': 1},
                        'bar': {'color': "darkblue"},
                        'steps': [
                            {'range': [0, 1.81], 'color': "#ffcccc", 'name': 'Distress'},
                            {'range': [1.81, 2.99], 'color': "#ffffcc", 'name': 'Grey'},
                            {'range': [2.99, 6], 'color': "#ccffcc", 'name': 'Safe'}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': 1.81
                        }
                    }
                ))
                
                # Add annotations for zones
                fig.add_annotation(
                    x=0.2, y=0.1,
                    text="Distress<br>Zone",
                    showarrow=False,
                    font=dict(size=10, color="red")
                )
                fig.add_annotation(
                    x=0.5, y=0.1,
                    text="Grey<br>Zone",
                    showarrow=False,
                    font=dict(size=10, color="orange")
                )
                fig.add_annotation(
                    x=0.8, y=0.1,
                    text="Safe<br>Zone",
                    showarrow=False,
                    font=dict(size=10, color="green")
                )
                
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                st.markdown("**Zone Thresholds:**")
                st.markdown(f"- **Safe**: Z > 2.99")
                st.markdown(f"- **Grey**: 1.81 - 2.99")
                st.markdown(f"- **Distress**: Z < 1.81")
                
                st.markdown("\n**Current Position:**")
                if altman['risk_level'] == 'Low':
                    st.success(f"✅ {ticker_input} is in the Safe Zone with low bankruptcy risk.")
                elif altman['risk_level'] == 'Moderate':
                    st.warning(f"⚠️ {ticker_input} is in the Grey Zone with moderate risk.")
                else:
                    st.error(f"🔴 {ticker_input} is in the Distress Zone with high bankruptcy risk.")
            
            st.divider()
            
            # Component breakdown
            st.subheader("Z-Score Component Analysis")
            
            components = altman.get('components', {})
            weighted = altman.get('weighted_components', {})
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Component ratios
                st.markdown("**Financial Ratios:**")
                
                ratio_df = pd.DataFrame({
                    'Component': [
                        'Working Capital / Total Assets',
                        'Retained Earnings / Total Assets',
                        'EBIT / Total Assets',
                        'Market Value / Total Liabilities',
                        'Sales / Total Assets'
                    ],
                    'Ratio': [
                        components.get('working_capital_ratio', 0),
                        components.get('retained_earnings_ratio', 0),
                        components.get('ebit_ratio', 0),
                        components.get('market_value_ratio', 0),
                        components.get('asset_turnover', 0)
                    ]
                })
                
                st.dataframe(ratio_df, use_container_width=True, hide_index=True)
            
            with col2:
                # Weighted contributions
                st.markdown("**Weighted Contributions to Z-Score:**")
                
                contrib_df = pd.DataFrame({
                    'Component': ['WC (×1.2)', 'RE (×1.4)', 'EBIT (×3.3)', 'MVE (×0.6)', 'Sales (×1.0)'],
                    'Contribution': [
                        weighted.get('wc_contribution', 0),
                        weighted.get('re_contribution', 0),
                        weighted.get('ebit_contribution', 0),
                        weighted.get('mv_contribution', 0),
                        weighted.get('sales_contribution', 0)
                    ]
                })
                
                fig = px.bar(
                    contrib_df,
                    x='Component',
                    y='Contribution',
                    color='Contribution',
                    color_continuous_scale='RdYlGn',
                    title="Component Contributions"
                )
                fig.update_layout(height=300, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)

else:
    st.info("👆 Enter a ticker symbol in the sidebar to begin financial health analysis.")

# Footer
st.divider()
st.markdown("""
**About Financial Health Scoring**

This dashboard uses two established metrics to evaluate company financial health:

- **Piotroski F-Score**: Developed by Professor Joseph Piotroski (University of Chicago), measures fundamental strength across profitability, leverage, and efficiency. Scores of 7-9 historically outperform the market.

- **Altman Z-Score**: Created by Professor Edward Altman (NYU Stern), predicts bankruptcy risk within 2 years with 72-80% accuracy. Used by credit analysts worldwide.

*Data source: SEC EDGAR (Company Facts API). Scores calculated from most recent annual filings (10-K).*
""")
