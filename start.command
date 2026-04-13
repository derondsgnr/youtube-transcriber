#!/bin/bash
cd "$(dirname "$0")"
if [ ! -d "venv" ]; then
  echo "No venv found. Run once: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
  read -r
  exit 1
fi
source venv/bin/activate
exec streamlit run app.py
