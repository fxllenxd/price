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
    cleaned = re.sub(currency_patterns, '', query, flags=i)
    # Remove extra spaces
    return " ".join(cleaned.split())

# --- PRICE HELPERS ---
def parse_price_float(price_str: str) -> float | None:
    """Parses raw text into a clean floating-point price value."""
    if not price_str:
        return None
    # Remove all non-numeric characters except dots and commas
    cleaned = re.sub(r'[^\d.,]', '', price_str)
    if not cleaned:
        return None
    
    # Handle European formatting (e.g. 1.250,50 -> 1250.50 or 500,00 -> 500.00)
    if ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace('.', '').replace(',', '.')
    elif ',' in cleaned:
        cleaned = cleaned.replace(',', '.')
        
    try:
        return float(cleaned)
    except ValueError:
        return None

# --- SCRAPER MODULES ---

def scrape_pazaruvaj(query: str):
    """Scrapes Pazaruvaj.com (Bulgaria's primary price comparison engine)"""
    results = []
    encoded_q = urllib.parse.quote(query)
    url = f"https://www.pazaruvaj.com/CategorySearch.php?st={encoded_q}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            products = soup.select('.product-box, .product-box-app, .product-box-small')
            for p in products[:5]:
                title_elem = p.select_one('.title-box a, .name')
                price_elem = p.select_one('.price')
                link_elem = p.select_one('a')
                
                if title_elem and price_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    price_val = parse_price_float(price_elem.get_text(strip=True))
                    link = link_elem.get('href', '')
                    if link and not link.startswith('http'):
                        link = "https://www.pazaruvaj.com" + link
                    
                    if price_val:
                        # Pazaruvaj defaults to BGN (or EUR converted)
                        results.append({
                            "title": title,
                            "price_eur": round(price_val / BGN_TO_EUR_RATE, 2),
                            "price_bgn": round(price_val, 2),
                            "source": "Pazaruvaj.com (.bg)",
                            "link": link
                        })
    except Exception:
        pass
    return results

def scrape_olx_bg(query: str):
    """Scrapes OLX Bulgaria (olx.bg) classifieds"""
    results = []
    encoded_q = urllib.parse.quote(query)
    url = f"https://www.olx.bg/ads/q-{encoded_q}/"
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            cards = soup.select('[data-cy="l-card"]')
            for card in cards[:5]:
                title_elem = card.select_one('h6, h4')
                price_elem = card.select_one('[data-testid="ad-price"]')
                link_elem = card.select_one('a')
                
                if title_elem and price_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    price_text = price_elem.get_text(strip=True)
                    price_val = parse_price_float(price_text)
                    link = link_elem.get('href', '')
                    if link and not link.startswith('http'):
                        link = "https://www.olx.bg" + link
                        
                    if price_val:
                        # Determine if raw text was EUR or BGN
                        if '€' in price_text or 'eur' in price_text.lower():
                            eur = price_val
                            bgn = round(price_val * BGN_TO_EUR_RATE, 2)
                        else:
                            bgn = price_val
                            eur = round(price_val / BGN_TO_EUR_RATE, 2)
                            
                        results.append({
                            "title": title,
                            "price_eur": eur,
                            "price_bgn": bgn,
                            "source": "OLX Bulgaria (.bg)",
                            "link": link
                        })
    except Exception:
        pass
    return results

def scrape_bazar_bg(query: str):
    """Scrapes Bazar.bg marketplace"""
    results = []
    encoded_q = urllib.parse.quote(query)
    url = f"https://bazar.bg/obiavi?q={encoded_q}"
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.select('.item, .list-item')
            for item in items[:5]:
                title_elem = item.select_one('.title, .title-link')
                price_elem = item.select_one('.price')
                link_elem = item.select_one('a')
                
                if title_elem and price_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    price_val = parse_price_float(price_elem.get_text(strip=True))
                    link = link_elem.get('href', '')
                    if link and not link.startswith('http'):
                        link = "https://bazar.bg" + link
                        
                    if price_val:
                        results.append({
                            "title": title,
                            "price_eur": round(price_val / BGN_TO_EUR_RATE, 2),
                            "price_bgn": round(price_val, 2),
                            "source": "Bazar.bg (.bg)",
                            "link": link
                        })
    except Exception:
        pass
    return results

def scrape_ebay_eu(query: str):
    """Scrapes eBay European listings"""
    results = []
    encoded_q = urllib.parse.quote(query)
    url = f"https://www.ebay.de/sch/i.html?_nkw={encoded_q}&_sacat=0"
    try:
        res = requests.get(url, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            items = soup.select('.s-item')
            for item in items[1:6]:  # Skip first item (often placeholder)
                title_elem = item.select_one('.s-item__title')
                price_elem = item.select_one('.s-item__price')
                link_elem = item.select_one('.s-item__link')
                
                if title_elem and price_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    price_val = parse_price_float(price_elem.get_text(strip=True))
                    link = link_elem.get('href', '#')
                    
                    if price_val:
                        results.append({
                            "title": title,
                            "price_eur": round(price_val, 2),
                            "price_bgn": round(price_val * BGN_TO_EUR_RATE, 2),
                            "source": "eBay (Europe)",
                            "link": link
                        })
    except Exception:
        pass
    return results

# --- CONCURRENT AGGREGATOR ENGINE ---
def search_all_marketplaces(raw_query: str, country: str):
    clean_q = sanitize_query(raw_query)
    all_results = []
    
    # Run scrapers in parallel threads for high performance
    scrapers = [
        scrape_pazaruvaj,
        scrape_olx_bg,
        scrape_bazar_bg,
        scrape_ebay_eu
    ]
    
    with ThreadPoolExecutor(max_workers=len(scrapers)) as executor:
        future_to_scraper = {executor.submit(scraper, clean_q): scraper for scraper in scrapers}
        for future in as_completed(future_to_scraper):
            try:
                data = future.result()
                if data:
                    all_results.extend(data)
            except Exception:
                pass
                
    # Sort all results by price (Lowest to Highest)
    all_results.sort(key=lambda x: x['price_eur'])
    return clean_q, all_results

# --- STREAMLIT UI ---
def main():
    st.set_page_config(page_title="EU Product Price Aggregator", page_icon="🛒", layout="wide")
    
    st.title("🛒 Multi-Platform Price Aggregator")
    st.caption("Search local marketplaces (.bg), classifieds, and European cross-border sites at once.")

    # Input Form Controls
    col_input, col_country, col_btn = st.columns([4, 2, 1])
    
    with col_input:
        user_query = st.text_input("Enter Product Name:", value="MOZA R3 Bundle")
    with col_country:
        country = st.selectbox("Target Country:", ["Bulgaria 🇧🇬", "Germany 🇩🇪", "France 🇫🇷", "Other (EU) 🇪🇺"])
    with col_btn:
        st.write("") # Alignment spacer
        st.write("")
        search_pressed = st.button("Search", type="primary", use_container_width=True)

    if search_pressed and user_query:
        with st.spinner("Searching across marketplaces..."):
            clean_q, results = search_all_marketplaces(user_query, country)
            
        st.info(f"Searched for: **\"{clean_q}\"** *(Currency tokens automatically sanitized)*")
        
        if results:
            best_deal = results[0]
            
            # --- BEST DEAL HERO BANNER ---
            st.markdown("---")
            st.success("### 🏆 BEST DEAL FOUND")
            
            b_col1, b_col2 = st.columns([3, 1])
            with b_col1:
                st.markdown(f"**Product:** {best_deal['title']}")
                st.markdown(f"**Lowest Price:** **€{best_deal['price_eur']:.2f}** (~{best_deal['price_bgn']:.2f} лв / BGN)")
                st.markdown(f"**Available On:** `{best_deal['source']}`")
            with b_col2:
                st.write("")
                st.link_button("👉 Go to Best Deal", best_deal['link'], use_container_width=True)
            st.markdown("---")

            # --- RESULTS TABLE ---
            st.subheader(f"All Discovered Deals ({len(results)} found)")
            
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
            st.warning("No listings found. Try adjusting your search keywords.")

if __name__ == "__main__":
    main()
