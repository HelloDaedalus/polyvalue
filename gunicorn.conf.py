workers = 1
timeout = 120
bind = "0.0.0.0:" + __import__("os").environ.get("PORT", "10000")
