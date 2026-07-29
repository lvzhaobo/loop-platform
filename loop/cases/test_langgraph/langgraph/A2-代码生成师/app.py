import os
from flask import Flask, render_template
app = Flask(__name__)
PORT = int(os.environ.get("PORT", 5000))
@app.route("/")
def index():
    return render_template("index.html")
@app.route("/health")
def health():
    return {"status": "ok"}
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)