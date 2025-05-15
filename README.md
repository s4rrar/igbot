# 📸 Instagram Downloader Telegram Bot

A powerful Telegram bot that allows users to download Instagram **posts**, **reels**, and **videos**—even splitting large videos into parts compatible with Telegram's file size limits.

![Screenshot_2025_05_15_17_18_23_62_0b342c26d6c44f3c8d2de40eabb4e1da](https://github.com/user-attachments/assets/e9541887-f5ac-4f17-aac2-e89d9b173d58)


## 🚀 Features

* ✅ Download public Instagram **posts**, **reels**, and **videos**
* 🔄 Split large videos into parts to bypass Telegram’s 50MB limit
* 📥 Queue system to manage multiple user downloads
* ❌ Download cancellation support
* 🧠 Threaded downloads for better performance
* 🔒 User-specific download session management

## 🧩 Requirements

* Python 3.7+
* FFmpeg installed and available in system path

### Python Dependencies

Install required packages with:

```bash
pip install instaloader pyTelegramBotAPI
```

## ⚙️ Configuration

Edit the `API_TOKEN` in the Python script:

```python
API_TOKEN = "<YOUR_API_TOKEN>"
```

You can get this token from [BotFather](https://t.me/BotFather) on Telegram.

---

## 📦 Installation & Run

### 1. Clone the Repository

```bash
git clone https://github.com/s4rrar/igbot.git
cd igbot
```

### 2. Run the Script

```bash
python igbot.py
```

It will automatically install missing dependencies and start the bot.

---

## 📲 Bot Commands

* `/start` or `/help` – Show usage instructions
* `/ig <Instagram URL>` – Start downloading content
* `/cancel` – Cancel an active download
* `/queue` – Check your position in the waiting queue

---

## 🔐 Notes

* Only **public content** is supported (no login or private account access).
* The bot automatically splits videos larger than 50MB for Telegram delivery.
* If concurrent download slots are full, the user is added to a waiting queue.
* Stories are not supported without login due to Instagram restrictions.

---

## 👨‍💻 Developer

* **Telegram:** [@s4rrar](https://t.me/s4rrar)

---

## 📝 License

This project is for educational purposes only. Usage of this tool to download content you don’t own or have permission to access may violate Instagram’s Terms of Service.
