import io
import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed

# ─── CONFIG ──────────────────────────────────────────────────────────────────
LOGIN_URL = 'http://webpage.boledragon.com:8080/accounts/login/'
QUERY_URL = 'http://webpage.boledragon.com:8080/forever_new/query/'

# Credentials from Streamlit secrets\           
USER = st.secrets["credentials"]["username"]
PASS = st.secrets["credentials"]["password"]

# ─── DATA FETCH FUNCTION ─────────────────────────────────────────────────────
def fetch_user(session, uid):
    try:
        # Refresh CSRF on query page
        qpg = session.get(QUERY_URL)
        soup_q = BeautifulSoup(qpg.text, 'html.parser')
        tag_q = soup_q.find('input', {'name': 'csrfmiddlewaretoken'})
        if not tag_q or not tag_q.has_attr('value'):
            raise ValueError("Missing CSRF token on query page")
        csrf_q = tag_q['value']

        # Submit user ID
        resp = session.post(
            QUERY_URL,
            data={'csrfmiddlewaretoken': csrf_q, 'user_id': uid},
            headers={'Referer': QUERY_URL},
            timeout=10
        )
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Locate properties table
        p_tag = soup.find('p', string=lambda t: t and 'User properties' in t)
        if not p_tag:
            raise ValueError("No 'User properties' section found")
        tbl = p_tag.find_next_sibling('table')
        if not tbl:
            raise ValueError("No data table found after header")

        rows = tbl.find_all('tr')
        out = {'queried_user_id': uid}

        # First header/data block
        if len(rows) >= 2:
            keys = [th.get_text(strip=True) for th in rows[0].find_all('th')]
            vals = [td.get_text(strip=True) for td in rows[1].find_all('td')]
            out.update(zip(keys, vals))

        # Second header/data block
        if len(rows) >= 4:
            keys2 = [th.get_text(strip=True) for th in rows[2].find_all('th')]
            vals2 = [td.get_text(strip=True) for td in rows[3].find_all('td')]
            out.update(zip(keys2, vals2))

        return out

    except Exception as e:
        return {'queried_user_id': uid, 'error': str(e)}

# ─── APP LAYOUT & LOGIC ───────────────────────────────────────────────────────
st.title("Bulk User-ID Detail Fetcher")
uploaded = st.file_uploader("Upload your input_ids.xlsx", type="xlsx")

if uploaded:
    # Read IDs from first column
    df_ids = pd.read_excel(uploaded, dtype=str)
    user_ids = df_ids.iloc[:, 0].dropna().astype(str).tolist()

    # Login session
    session = requests.Session()
    lp = session.get(LOGIN_URL, timeout=10)
    soup_l = BeautifulSoup(lp.text, 'html.parser')
    tag_l = soup_l.find('input', {'name': 'csrfmiddlewaretoken'})
    csrf_l = tag_l['value'] if tag_l and tag_l.has_attr('value') else ''
    session.post(
        LOGIN_URL,
        data={'csrfmiddlewaretoken': csrf_l, 'username': USER, 'password': PASS},
        headers={'Referer': LOGIN_URL},
        timeout=10
    )

    # Fetch in parallel
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(fetch_user, session, uid) for uid in user_ids]
        results = [f.result() for f in as_completed(futures)]

    # Separate successes and errors
    errors = [r for r in results if 'error' in r]
    successes = [r for r in results if 'error' not in r]

    # Display errors
    if errors:
        st.error("Some IDs could not be fetched:")
        for err in errors:
            st.write(f"• ID {err['queried_user_id']}: {err['error']}")

    # Show and download successful results
    if successes:
        df_out = pd.DataFrame(successes)
        st.write("### Fetched User Data")
        st.dataframe(df_out)

        buffer = io.BytesIO()
        df_out.to_excel(buffer, index=False, engine='openpyxl')
        buffer.seek(0)
        st.download_button(
            label="Download results.xlsx",
            data=buffer.getvalue(),
            file_name="results.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    else:
        st.warning("No valid user properties were fetched.")
