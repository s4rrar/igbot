import os
import telebot
import instaloader
import threading
from queue import Queue
import tempfile
import shutil
import math
import subprocess
import re
import time
from datetime import datetime
from urllib.parse import urlparse

# Configuration
API_TOKEN = "<YOUR_API_TOKEN>"
MAX_TELEGRAM_SIZE = 50 * 1024 * 1024  # 50 MB in bytes
MAX_CONCURRENT_DOWNLOADS = 5  # Maximum concurrent downloads
MAX_QUEUE_SIZE = 50  # Maximum number of users in queue

# Thread-safe queues and tracking
download_queue = Queue()
waiting_queue = Queue(maxsize=MAX_QUEUE_SIZE)
user_downloads = {}  # Stores (message_id, cancel_event) tuple
download_lock = threading.Lock()
queue_lock = threading.Lock()
ig_instances = {}  # Store instaloader instances per user

bot = telebot.TeleBot(API_TOKEN)


def clear_screen():
    """Clear console and show bot started message"""
    os.system("cls" if os.name == "nt" else "clear")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Instagram Downloader Bot started...")
    print("Developer: @s4rrar")


def extract_instagram_url(text):
    """Extract Instagram URL from text"""
    # Match common Instagram URL patterns for posts, reels, stories
    patterns = [
        r'https?://(?:www\.)?instagram\.com/(?:p|reel|stories|reels)/[^/\s]+(?:/\S*)?',
        r'https?://(?:www\.)?instagr\.am/(?:p|reel|stories|reels)/[^/\s]+(?:/\S*)?'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def get_media_duration(filename):
    """Get media duration using ffprobe"""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        filename,
    ]
    try:
        output = subprocess.check_output(cmd).decode().strip()
        return float(output)
    except:
        return None


def split_video(input_file, max_size=MAX_TELEGRAM_SIZE):
    """Split a video file into parts that fit within Telegram's size limit"""
    if not os.path.exists(input_file):
        return []

    file_size = os.path.getsize(input_file)
    if file_size <= max_size:
        return [input_file]

    duration = get_media_duration(input_file)
    if not duration:
        return []

    safe_max_size = 45 * 1024 * 1024  # 45MB
    num_parts = math.ceil(file_size / safe_max_size)
    segment_duration = duration / num_parts

    output_files = []
    for i in range(num_parts):
        start_time = i * segment_duration
        output_file = f"{input_file[:-4]}_part{i+1}.mp4"

        cmd = [
            "ffmpeg",
            "-i",
            input_file,
            "-ss",
            str(start_time),
            "-t",
            str(segment_duration),
            "-c:v",
            "libx264",
            "-b:v",
            "1500k",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-max_muxing_queue_size",
            "1024",
            output_file,
            "-y",
        ]

        try:
            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                if os.path.getsize(output_file) > safe_max_size:
                    cmd[9] = "750k"  # Reduce video bitrate
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                if (
                    os.path.exists(output_file)
                    and os.path.getsize(output_file) <= MAX_TELEGRAM_SIZE
                ):
                    output_files.append(output_file)
                else:
                    os.remove(output_file)
        except Exception as e:
            print(f"Error splitting video: {e}")
            if os.path.exists(output_file):
                os.remove(output_file)

    return output_files


def is_instagram_url(url):
    """Check if URL is an Instagram URL"""
    parsed_url = urlparse(url)
    return parsed_url.netloc in ('instagram.com', 'www.instagram.com', 'instagr.am', 'www.instagr.am')


def get_content_type(url):
    """Determine if the URL is for a post, reel, or story"""
    if "/p/" in url:
        return "post"
    elif "/reel/" in url or "/reels/" in url:
        return "reel"
    elif "/stories/" in url:
        return "story"
    else:
        return "unknown"


def download_instagram_content(url, user_id, cancel_event=None):
    """Download Instagram content with progress updates and cancellation support"""
    try:
        if not is_instagram_url(url):
            return None, "Not a valid Instagram URL"

        # Create a temporary directory for downloads
        temp_dir = tempfile.mkdtemp()
        
        # Get or create instaloader instance for this user
        if user_id not in ig_instances:
            ig_instances[user_id] = instaloader.Instaloader(
                download_videos=True,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
                post_metadata_txt_pattern='',
                storyitem_metadata_txt_pattern='',
                dirname_pattern=temp_dir
            )
        
        loader = ig_instances[user_id]
        content_type = get_content_type(url)
        
        # Extract shortcode (post ID) from URL
        shortcode = None
        if content_type in ["post", "reel"]:
            pattern = r'/(?:p|reel|reels)/([^/]+)'
            match = re.search(pattern, url)
            if match:
                shortcode = match.group(1)
        elif content_type == "story":
            # Stories are more complex and may require login
            return None, "Story downloads require login. Please use posts and reels only."
        
        if not shortcode:
            return None, "Could not extract content ID from URL"
            
        if cancel_event and cancel_event.is_set():
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None, "Download cancelled"
            
        # Download the post
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        
        if cancel_event and cancel_event.is_set():
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None, "Download cancelled"
            
        # Download the post to the temp directory
        loader.download_post(post, target=temp_dir)
        
        # Find downloaded files
        media_files = []
        for file in os.listdir(temp_dir):
            filepath = os.path.join(temp_dir, file)
            if os.path.isfile(filepath) and not file.endswith(('.json', '.txt')):
                if file.endswith(('.jpg', '.jpeg', '.png')):
                    media_files.append((filepath, "image"))
                elif file.endswith(('.mp4', '.mov')):
                    media_files.append((filepath, "video"))
        
        if not media_files:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None, "No media found in download"
            
        caption = f"Downloaded from Instagram\nUsername: @{post.owner_username}\n"
        
        return (media_files, temp_dir, caption), None
        
    except instaloader.exceptions.InstaloaderException as e:
        return None, f"Instagram error: {str(e)}"
    except Exception as e:
        return None, f"Error downloading: {str(e)}"


def download_worker():
    """Background worker to process download queue"""
    while True:
        task = download_queue.get()

        try:
            user_id, message, url, cancel_event = task

            content_type = get_content_type(url)
            
            bot.edit_message_text(
                f"⏳ Downloading Instagram {content_type}...",
                message.chat.id,
                message.message_id,
            )

            if cancel_event.is_set():
                bot.edit_message_text(
                    "❌ Download cancelled.", message.chat.id, message.message_id
                )
                continue

            result, error = download_instagram_content(url, user_id, cancel_event)

            if cancel_event.is_set():
                bot.edit_message_text(
                    "❌ Download cancelled.", message.chat.id, message.message_id
                )
            elif error:
                bot.edit_message_text(
                    f"❌ Download failed: {error}", message.chat.id, message.message_id
                )
            elif result:
                media_files, temp_dir, caption = result
                
                bot.edit_message_text(
                    f"📤 Found {len(media_files)} media file(s). Sending...",
                    message.chat.id,
                    message.message_id,
                )
                
                # Process each media file
                for idx, (filepath, media_type) in enumerate(media_files):
                    if cancel_event.is_set():
                        break
                        
                    caption_with_idx = f"{caption}Item {idx+1}/{len(media_files)}"
                    file_size = os.path.getsize(filepath)
                    
                    # Handle files larger than Telegram's limit
                    if media_type == "video" and file_size > MAX_TELEGRAM_SIZE:
                        bot.edit_message_text(
                            f"📦 Video is too large for Telegram. Splitting into parts...\n⏳ Please be patient.",
                            message.chat.id,
                            message.message_id,
                        )
                        
                        parts = split_video(filepath)
                        total_parts = len(parts)
                        
                        if total_parts == 0:
                            bot.send_message(
                                message.chat.id,
                                f"❌ Error splitting video. File might be corrupted."
                            )
                            continue
                            
                        for i, part in enumerate(parts, 1):
                            if cancel_event.is_set():
                                break
                                
                            bot.edit_message_text(
                                f"📤 Sending part {i}/{total_parts}...",
                                message.chat.id,
                                message.message_id,
                            )
                            
                            with open(part, "rb") as file:
                                part_caption = f"{caption_with_idx} - Part {i}/{total_parts}"
                                bot.send_video(message.chat.id, file, caption=part_caption)
                                
                            # Small delay to prevent flooding
                            time.sleep(1)
                            
                            # Clean up this part
                            if os.path.exists(part):
                                os.remove(part)
                    else:
                        # Send file normally
                        with open(filepath, "rb") as file:
                            if media_type == "image":
                                bot.send_photo(message.chat.id, file, caption=caption_with_idx)
                            else:  # video
                                bot.send_video(message.chat.id, file, caption=caption_with_idx)
                        
                        # Small delay to prevent flooding
                        time.sleep(1)
                
                # Clean up temp directory
                shutil.rmtree(temp_dir, ignore_errors=True)
                
                if not cancel_event.is_set():
                    bot.edit_message_text(
                        f"✅ Download completed! Sent {len(media_files)} media file(s).",
                        message.chat.id,
                        message.message_id,
                    )
            else:
                bot.edit_message_text(
                    "❌ Download failed. Possible reasons:\n"
                    "• Invalid Instagram URL\n"
                    "• Content unavailable\n"
                    "• Private account\n"
                    "• Network issues",
                    message.chat.id,
                    message.message_id,
                )
        except Exception as e:
            print(f"Download worker error: {e}")
            bot.edit_message_text(
                f"An unexpected error occurred: {str(e)}",
                message.chat.id,
                message.message_id
            )
        finally:
            with download_lock:
                if user_id in user_downloads:
                    user_downloads.pop(user_id, None)

            download_queue.task_done()

            # Process next user in waiting queue
            process_waiting_queue()


def process_waiting_queue():
    """Process users in waiting queue when a slot becomes available"""
    with queue_lock:
        if not waiting_queue.empty() and len(user_downloads) < MAX_CONCURRENT_DOWNLOADS:
            try:
                task = waiting_queue.get_nowait()
                user_id, message, url, cancel_event = task

                # Notify user their download is starting
                bot.edit_message_text(
                    "Your turn has arrived! Starting download... 🔄",
                    message.chat.id,
                    message.message_id,
                )

                # Add to active downloads
                with download_lock:
                    user_downloads[user_id] = (message.message_id, cancel_event)

                # Add to download queue
                download_queue.put(task)

                return True
            except:
                return False
    return False


@bot.message_handler(commands=["queue"])
def check_queue_position(message):
    """Allow users to check their position in the queue"""
    user_id = message.from_user.id

    # Check if user is in active downloads
    if user_id in user_downloads:
        bot.reply_to(message, "Your download is currently in progress! ⏳")
        return

    # Check waiting queue
    position = 1
    found = False
    temp_queue = Queue()

    while not waiting_queue.empty():
        task = waiting_queue.get()
        if task[0] == user_id:
            found = True
        temp_queue.put(task)
        if not found:
            position += 1

    # Restore queue
    while not temp_queue.empty():
        waiting_queue.put(temp_queue.get())

    if found:
        bot.reply_to(
            message, f"You are position #{position} in the queue. Please wait... ⌛"
        )
    else:
        bot.reply_to(message, "You are not currently in the queue.")


@bot.message_handler(commands=["cancel"])
def cancel_download(message):
    """Handle download cancellation requests"""
    user_id = message.from_user.id

    with download_lock:
        if user_id not in user_downloads:
            bot.reply_to(message, "❌ You don't have any active downloads to cancel.")
            return

        message_id, cancel_event = user_downloads[user_id]
        cancel_event.set()
        bot.reply_to(message, "🛑 Cancelling your download...")


@bot.message_handler(commands=["help", "start"])
def send_welcome(message):
    """Welcome message with bot instructions"""
    welcome_text = """
Hi there! I'm Instagram Downloader Bot 📸

I can help you download Instagram content:
• Use /ig [Instagram URL] to download content
• Use /cancel to cancel your current download
• Use /queue to check your position in queue

Examples:
/ig https://www.instagram.com/p/ABC123/
/ig https://www.instagram.com/reel/XYZ789/

Note: 
- Downloading requires a public Instagram post
- Large videos will be split into parts due to Telegram's size limit
- If the system is busy, you'll be placed in a queue
- Works in both private chats and group chats
"""
    bot.reply_to(message, welcome_text)


@bot.message_handler(commands=["ig"])
def handle_ig_command(message):
    """Handle /ig command with Instagram URL"""
    try:
        # Get text after the command
        command_parts = message.text.split(maxsplit=1)
        if len(command_parts) < 2:
            bot.reply_to(
                message,
                "❌ Please provide an Instagram URL after the /ig command.\nExample: /ig https://www.instagram.com/reel/ABC123/"
            )
            return
            
        # Extract Instagram URL from the text after command
        url = extract_instagram_url(command_parts[1])
        if not url:
            bot.reply_to(
                message, 
                "❌ No valid Instagram URL detected. Please use format: /ig [Instagram URL]"
            )
            return
            
        user_id = message.from_user.id
        
        # Check for ongoing downloads
        with download_lock:
            if user_id in user_downloads:
                bot.reply_to(
                    message,
                    "❌ You already have a download in progress. Use /cancel to stop it.",
                )
                return
        
        # Create cancellation event and processing message
        cancel_event = threading.Event()
        processing_msg = bot.reply_to(message, "Processing your Instagram URL... 🔄")
        
        # Check if there's room for immediate processing
        with download_lock:
            if len(user_downloads) < MAX_CONCURRENT_DOWNLOADS:
                user_downloads[user_id] = (processing_msg.message_id, cancel_event)
                download_queue.put(
                    (user_id, processing_msg, url, cancel_event)
                )
            else:
                # Try to add to waiting queue
                try:
                    waiting_queue.put_nowait(
                        (user_id, processing_msg, url, cancel_event)
                    )
                    queue_position = waiting_queue.qsize()
                    bot.edit_message_text(
                        f"Queue is full. You are position #{queue_position} in line.\n"
                        f"Use /queue to check your position.\n"
                        f"Your download will start automatically when it's your turn.",
                        processing_msg.chat.id,
                        processing_msg.message_id,
                    )
                except Queue.Full:
                    bot.edit_message_text(
                        "❌ Sorry, the waiting queue is full. Please try again later.",
                        processing_msg.chat.id,
                        processing_msg.message_id,
                    )
    except Exception as e:
        bot.reply_to(message, f"An unexpected error occurred: {e}")


# Start download workers
for _ in range(MAX_CONCURRENT_DOWNLOADS):
    worker_thread = threading.Thread(target=download_worker, daemon=True)
    worker_thread.start()

# Start the bot
if __name__ == "__main__":
    clear_screen()
    print("Installing required packages...")
    try:
        import subprocess
        subprocess.check_call(["pip", "install", "instaloader", "pyTelegramBotAPI"])
    except Exception as e:
        print(f"Error installing packages: {e}")
    
    clear_screen()
    bot.infinity_polling()
