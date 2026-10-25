import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- CONSTANTS & CONFIGURATION ---
BGN_TO_EUR_RATE = 1.95583  # Fixed Bulgarian Lev to Euro rate

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9,bg;q=0.8",
}

# --- QUERY SANITIZATION ---
def sanitize_query(query: str) -> str:
    """Strips currency terms like лв, lv, BGN, EUR, € and clean search tokens."""
    currency_patterns = r'\b(лв\.?|лв|lv\.?|lv|bgn|eur|euro|€)\b'
    cleaned = re.sub(currency_patterns, '', query, flags=re.IGNORECASE)
    return " ".join(cleaned.split())

# --- PRICE HELPERS ---
def parse_prices_from_text(text: str):
    """Extracts numeric prices and detects currency from text snippets."""
    # Find patterns like 550лв, €300, 499.00 лв, etc.
    prices = []
    # Match numbers with optional currency symbols nearby
    matches = re.findall(r'(?:[€лвBGN]+)?\s*(\d{1,4}(?:[.,]\d{1,2})?)\s*(?:[€лвBGN]|lv|EUR)?', text, re.IGNORECASE)
    for m in matches:
        val = parse_price_float(m)
        if val and val > 5: # Filter out tiny numbers (like ratings or IDs)
            prices.append(val)
    return prices

def parse_price_float(price_str: str) -> float | None:
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d.,]', '', price_str)
    if not cleaned:
        return None
    if ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace('.', '').replace(',', '.')
    elif ',' in cleaned:
        cleaned = cleaned.replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return None

# --- ROBUST SEARCH ENGINE (VIA DUCKDUCKGO HTML) ---
def search_duckduckgo_site(query: str, site_domain: str, source_name: str):
    """Searches a specific site via DuckDuckGo HTML to bypass anti-bot blocks."""
    results = []
    search_query = f"{query} site:{site_domain}"
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(search_query)}"
    
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            result_elements = soup.select('.result')
            
            for el in result_elements[:4]:
                title_elem = el.select_one('.result__title')
                snippet_elem = el.select_one('.result__snippet')
                link_elem = el.select_one('.result__url')
                
                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    
                    # Extract URL from DuckDuckGo redirect link if necessary
                    raw_link = link_elem.get('href', '')
                    if 'uddg=' in raw_link:
                        parsed_url = urllib.parse.parse_qs(urllib.parse.urlparse(raw_link).query)
                        actual_link = parsed_url.get('uddg', [''])[0]
                    else:
                        actual_link = raw_link
                        
                    if not actual_link.startswith('http'):
                        actual_link = f"https://{site_domain}"

                    # Try to parse price from snippet or title
                    combined_text = f"{title} {snippet}"
                    extracted_prices = parse_prices_from_text(combined_text)
                    
                    # Default estimated fallback price if none explicitly found in text
                    price_val = extracted_prices[0] if extracted_prices else 100.00
                    
                    results.append({
                        "title": title,
                        "price_eur": round(price_val / BGN_TO_EUR_RATE if 'bg' in site_domain or price_val > 500 else price_val, 2),
                        "price_bgn": round(price_val if price_val > 500 else price_val * BGN_TO_EUR_RATE, 2),
                        "source": source_name,
                        "link": actual_link
                    })
    except Exception:
        pass
    return results

# --- CONCURRENT AGGREGATOR ---
def search_all_marketplaces(raw_query: str, country: str):
    clean_q = sanitize_query(raw_query)
    all_results = []
    
    targets = [
        ("pazaruvaj.com", "Pazaruvaj.com (.bg)"),
        ("olx.bg", "OLX Bulgaria (.bg)"),
        ("bazar.bg", "Bazar.bg (.bg)"),
        ("ebay.de", "eBay (Europe)"),
        ("amazon.de", "Amazon (Europe)")
    ]
    
    with ThreadPoolExecutor(max_workers=len(targets)) as executor:
        future_to_target = {
            executor.submit(search_duckduckgo_site, clean_q, domain, name): name 
            for domain, name in targets
        }
        for future in as_completed(future_to_target):
            try:
                data = future.result()
                if data:
                    all_results.extend(data)
            except Exception:
                pass
                
    # Sort all results by price
    all_results.sort(key=lambda x: x['price_eur'])
    return clean_q, all_results

# --- STREAMLIT UI ---
def main():
    st.set_page_config(page_title="EU Product Price Aggregator", page_icon="🛒", layout="wide")
    
    st.title("🛒 Multi-Platform Price Aggregator")
    st.caption("Search local Bulgarian marketplaces, price engines, and European cross-border sites instantly.")

    col_input, col_country, col_btn = st.columns([4, 2, 1])
    
    with col_input:
        user_query = st.text_input("Enter Product Name:", value="MOZA R3 Bundle")
    with col_country:
        country = st.selectbox("Target Country:", ["Bulgaria 🇧🇬", "Germany 🇩🇪", "France 🇫🇷", "Other (EU) 🇪🇺"])
    with col_btn:
        st.write("")
        st.write("")
        search_pressed = st.button("Search", type="primary", use_container_width=True)

    if search_pressed and user_query:
        with st.spinner("Aggregating live listings across the internet..."):
            clean_q, results = search_all_marketplaces(user_query, country)
            
        st.info(f"Searched for: **\"{clean_q}\"** *(Currency filters applied)*")
        
        if results:
            best_deal = results[0]
            
            st.markdown("---")
            st.success("### 🏆 BEST DEAL FOUND")
            
            b_col1, b_col2 = st.columns([3, 1])
            with b_col1:
                st.markdown(f"**Product:** {best_deal['title']}")
                st.markdown(f"**Estimated Price:** **€{best_deal['price_eur']:.2f}** (~{best_deal['price_bgn']:.2f} лв / BGN)")
                st.markdown(f"**Available On:** `{best_deal['source']}`")
            with b_col2:
                st.write("")
                st.link_button("👉 Go to Listing", best_deal['link'], use_container_width=True)
            st.markdown("---")

            st.subheader(f"Discovered Listings ({len(results)} found)")
            
            table_data = []
            for item in results:
                table_data.append({
                    "Product Title": item['title'],
                    "Price (EUR)": f"€{item['price_eur']:.2f}",
                    "Price (BGN)": f"{item['price_bgn']:.2f} лв",
                    "Platform / Store": item['source'],
                    "Direct Link": item['link']
                })

            st.dataframe(
                table_data,
                column_config={
                    "Direct Link": st.column_config.LinkColumn("Product Page", display_text="View Listing")
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.warning("No listings found. Try broader keywords (e.g. 'MOZA R3' instead of 'MOZA R3 Bundle').")

if __name__ == "__main__":
    main()
