import streamlit as st
import pandas as pd
from datetime import datetime
import pdfplumber
import requests
from sqlalchemy import create_engine, text

st.set_page_config(layout="wide")

# --- MySQL Database Configuration ---
DB_USER = st.secrets.mysql.DB_USER
DB_PASSWORD = st.secrets.mysql.DB_PASSWORD
DB_HOST = st.secrets.mysql.DB_HOST
DB_PORT = st.secrets.mysql.DB_PORT
DB_NAME = st.secrets.mysql.DB_NAME

# SQLAlchemy connection string for MySQL using mysql-connector
DATABASE_URL = (
    f"mysql+mysqlconnector://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# Create the engine
engine = create_engine(DATABASE_URL, echo=False)


# Function to create table if not exists
def create_table_if_not_exists():
    create_table_query = """
    CREATE TABLE IF NOT EXISTS summaries (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        summary TEXT NOT NULL,
        date DATE NOT NULL
    );
    """
    with engine.connect() as conn:
        conn.execute(text(create_table_query))
        conn.commit()


# Load saved summaries from DB into a DataFrame
def load_saved_summaries():
    query = text("SELECT name, summary, date FROM summaries;")
    with engine.connect() as conn:
        df = pd.read_sql(query, conn)
    return df


# Insert a new summary record into the database
def save_summary_to_db(name, summary, date_str):
    insert_query = """
    INSERT INTO summaries (name, summary, date)
    VALUES (:name, :summary, :date);
    """
    with engine.connect() as conn:
        conn.execute(
            text(insert_query), {"name": name, "summary": summary, "date": date_str}
        )
        conn.commit()


# --- Perplexity API functions ---
API_KEY = "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"
API_URL = "https://api.perplexity.ai/chat/completions"


def generate_summary_with_perplexity(text, model="sonar-pro", max_tokens=8000):
    """
    Generate a summary using Perplexity AI's Chat Completions API.
    We instruct the model to "Please summarize the following text:" followed by the input.
    """
    prompt = f"Please summarize the following text:\n\n{text}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    response = requests.post(API_URL, json=payload, headers=headers)
    if response.status_code != 200:
        st.error(f"Error from Perplexity API: {response.status_code} {response.text}")
        return None
    result = response.json()
    summary = result["choices"][0]["message"]["content"].strip()
    return summary


def extract_text_from_pdf(pdf_file):
    """Extract text from each page of the PDF using pdfplumber."""
    text = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text


def main():
    # Create DB table if it doesn't exist
    create_table_if_not_exists()

    # Load saved summaries from the database into session state
    if "saved_results" not in st.session_state:
        st.session_state.saved_results = load_saved_summaries()
    if "generated_summary" not in st.session_state:
        st.session_state.generated_summary = None

    st.title("Document Abstraction AI Agent")
    st.markdown(
        "Upload a PDF document (or enter text) to generate a summary using Perplexity AI's sonar-pro model. Summaries are saved permanently to a MySQL database."
    )

    # Move file upload to sidebar
    st.sidebar.image("Eunoia.png",  use_container_width=True)

    with st.sidebar:
        st.header("Upload Document")
        uploaded_file = st.file_uploader("Upload a PDF", type="pdf")
    
    # Process the uploaded file
    pdf_text = ""
    if uploaded_file is not None:
        pdf_text = extract_text_from_pdf(uploaded_file)
        st.subheader("Extracted PDF Text")
        st.write(pdf_text)

    # Allow user to also enter additional text manually
    input_text = st.text_area("Or enter text to summarize:", height=200)

    # Combine text from PDF and manual input if both are provided
    if pdf_text and input_text:
        combined_text = pdf_text + "\n" + input_text
    elif pdf_text:
        combined_text = pdf_text
    else:
        combined_text = input_text

    # Generate Summary Button
    if st.button("Generate Summary"):
        if not combined_text.strip():
            st.error("Please provide text input or upload a valid PDF file.")
        else:
            with st.spinner("Generating summary using Perplexity AI..."):
                summary = generate_summary_with_perplexity(
                    combined_text, model="sonar-pro", max_tokens=8000
                )
                if summary:
                    st.subheader("Generated Summary")
                    st.write(summary)
                    st.session_state.generated_summary = summary

    # Allow user to save the generated summary (display only if a summary has been generated)
    if st.session_state.generated_summary is not None:
        st.markdown("### Save Generated Summary")
        custom_name = st.text_input("Custom Name for Saved Summary", key="custom_name")
        custom_date = st.date_input("Date", value=datetime.today(), key="custom_date")
        if st.button("Save Summary"):
            entry_name = (
                custom_name
                if custom_name
                else f"Summary {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            date_str = custom_date.strftime("%Y-%m-%d")
            # Save to MySQL DB
            save_summary_to_db(entry_name, st.session_state.generated_summary, date_str)
            st.success("Summary saved successfully!")
            # Refresh session state from DB
            st.session_state.saved_results = load_saved_summaries()

    # Display saved summaries in a collapsible section
    st.markdown("### Saved Insights")
    with st.expander("Click to view saved summaries"):
        if st.session_state.saved_results.empty:
            st.info("No summaries saved yet.")
        else:
            st.dataframe(st.session_state.saved_results)


if __name__ == "__main__":
    main()
