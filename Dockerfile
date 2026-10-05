FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home appuser && mkdir /data && chown appuser:appuser /data
COPY app.py auth.py database.py setup_owner.py ./
COPY .streamlit/config.toml .streamlit/config.toml
USER appuser
ENV EXPENSE_DB_PATH=/data/harcamalar.db
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
