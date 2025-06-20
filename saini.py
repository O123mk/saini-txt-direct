import os
import re
import time
import mmap
import datetime
import aiohttp
import aiofiles
import asyncio
import logging
import requests
import tgcrypto
import subprocess
import concurrent.futures
from math import ceil
from utils import progress_bar
from pyrogram import Client, filters
from pyrogram.types import Message
from io import BytesIO
from pathlib import Path  
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode
from PIL import Image, ImageDraw, ImageFont
import logging

# Setup logging to console and file
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler('bot.log')  # Save logs to bot.log
    ]
)
logger = logging.getLogger(__name__)

def duration(filename):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                             "format=duration", "-of",
                             "default=noprint_wrappers=1:nokey=1", filename],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT)
    return float(result.stdout)

def get_mps_and_keys(api_url):
    response = requests.get(api_url)
    response_json = response.json()
    mpd = response_json.get('MPD')
    keys = response_json.get('KEYS')
    return mpd, keys
   
def exec(cmd):
        process = subprocess.run(cmd, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        output = process.stdout.decode()
        print(output)
        return output
        #err = process.stdout.decode()
def pull_run(work, cmds):
    with concurrent.futures.ThreadPoolExecutor(max_workers=work) as executor:
        print("Waiting for tasks to complete")
        fut = executor.map(exec,cmds)
async def aio(url,name):
    k = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(k, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return k


async def download(url,name):
    ka = f'{name}.pdf'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                f = await aiofiles.open(ka, mode='wb')
                await f.write(await resp.read())
                await f.close()
    return ka

async def pdf_download(url, file_name, chunk_size=1024 * 10):
    if os.path.exists(file_name):
        os.remove(file_name)
    r = requests.get(url, allow_redirects=True, stream=True)
    with open(file_name, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                fd.write(chunk)
    return file_name   
   

def parse_vid_info(info):
    info = info.strip()
    info = info.split("\n")
    new_info = []
    temp = []
    for i in info:
        i = str(i)
        if "[" not in i and '---' not in i:
            while "  " in i:
                i = i.replace("  ", " ")
            i.strip()
            i = i.split("|")[0].split(" ",2)
            try:
                if "RESOLUTION" not in i[2] and i[2] not in temp and "audio" not in i[2]:
                    temp.append(i[2])
                    new_info.append((i[0], i[2]))
            except:
                pass
    return new_info


def vid_info(info):
    info = info.strip()
    info = info.split("\n")
    new_info = dict()
    temp = []
    for i in info:
        i = str(i)
        if "[" not in i and '---' not in i:
            while "  " in i:
                i = i.replace("  ", " ")
            i.strip()
            i = i.split("|")[0].split(" ",3)
            try:
                if "RESOLUTION" not in i[2] and i[2] not in temp and "audio" not in i[2]:
                    temp.append(i[2])
                    
                    # temp.update(f'{i[2]}')
                    # new_info.append((i[2], i[0]))
                    #  mp4,mkv etc ==== f"({i[1]})" 
                    
                    new_info.update({f'{i[2]}':f'{i[0]}'})

            except:
                pass
    return new_info


async def decrypt_and_merge_video(mpd_url, keys_string, output_path, output_name, quality="720"):
    try:
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        cmd1 = f'yt-dlp -f "bv[height<={quality}]+ba/b" -o "{output_path}/file.%(ext)s" --allow-unplayable-format --no-check-certificate --external-downloader aria2c "{mpd_url}"'
        print(f"Running command: {cmd1}")
        os.system(cmd1)
        
        avDir = list(output_path.iterdir())
        print(f"Downloaded files: {avDir}")
        print("Decrypting")

        video_decrypted = False
        audio_decrypted = False

        for data in avDir:
            if data.suffix == ".mp4" and not video_decrypted:
                cmd2 = f'mp4decrypt {keys_string} --show-progress "{data}" "{output_path}/video.mp4"'
                print(f"Running command: {cmd2}")
                os.system(cmd2)
                if (output_path / "video.mp4").exists():
                    video_decrypted = True
                data.unlink()
            elif data.suffix == ".m4a" and not audio_decrypted:
                cmd3 = f'mp4decrypt {keys_string} --show-progress "{data}" "{output_path}/audio.m4a"'
                print(f"Running command: {cmd3}")
                os.system(cmd3)
                if (output_path / "audio.m4a").exists():
                    audio_decrypted = True
                data.unlink()

        if not video_decrypted or not audio_decrypted:
            raise FileNotFoundError("Decryption failed: video or audio file not found.")

        cmd4 = f'ffmpeg -i "{output_path}/video.mp4" -i "{output_path}/audio.m4a" -c copy "{output_path}/{output_name}.mp4"'
        print(f"Running command: {cmd4}")
        os.system(cmd4)
        if (output_path / "video.mp4").exists():
            (output_path / "video.mp4").unlink()
        if (output_path / "audio.m4a").exists():
            (output_path / "audio.m4a").unlink()
        
        filename = output_path / f"{output_name}.mp4"

        if not filename.exists():
            raise FileNotFoundError("Merged video file not found.")

        cmd5 = f'ffmpeg -i "{filename}" 2>&1 | grep "Duration"'
        duration_info = os.popen(cmd5).read()
        print(f"Duration info: {duration_info}")

        return str(filename)

    except Exception as e:
        print(f"Error during decryption and merging: {str(e)}")
        raise

async def run(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    stdout, stderr = await proc.communicate()

    print(f'[{cmd!r} exited with {proc.returncode}]')
    if proc.returncode == 1:
        return False
    if stdout:
        return f'[stdout]\n{stdout.decode()}'
    if stderr:
        return f'[stderr]\n{stderr.decode()}'

    

def old_download(url, file_name, chunk_size = 1024 * 10):
    if os.path.exists(file_name):
        os.remove(file_name)
    r = requests.get(url, allow_redirects=True, stream=True)
    with open(file_name, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=chunk_size):
            if chunk:
                fd.write(chunk)
    return file_name


def human_readable_size(size, decimal_places=2):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if size < 1024.0 or unit == 'PB':
            break
        size /= 1024.0
    return f"{size:.{decimal_places}f} {unit}"


def time_name():
    date = datetime.date.today()
    now = datetime.datetime.now()
    current_time = now.strftime("%H%M%S")
    return f"{date} {current_time}.mp4"


async def download_video(url,cmd, name):
    download_cmd = f'{cmd} -R 25 --fragment-retries 25 --external-downloader aria2c --downloader-args "aria2c: -x 16 -j 32"'
    global failed_counter
    print(download_cmd)
    logging.info(download_cmd)
    k = subprocess.run(download_cmd, shell=True)
    if "visionias" in cmd and k.returncode != 0 and failed_counter <= 10:
        failed_counter += 1
        await asyncio.sleep(5)
        await download_video(url, cmd, name)
    failed_counter = 0
    try:
        if os.path.isfile(name):
            return name
        elif os.path.isfile(f"{name}.webm"):
            return f"{name}.webm"
        name = name.split(".")[0]
        if os.path.isfile(f"{name}.mkv"):
            return f"{name}.mkv"
        elif os.path.isfile(f"{name}.mp4"):
            return f"{name}.mp4"
        elif os.path.isfile(f"{name}.mp4.webm"):
            return f"{name}.mp4.webm"

        return name
    except FileNotFoundError as exc:
        return os.path.isfile.splitext[0] + "." + "mp4"


async def send_doc(bot: Client, m: Message, cc, ka, cc1, prog, count, name, channel_id):
    reply = await bot.send_message(channel_id, f"Downloading pdf:\n<pre><code>{name}</code></pre>")
    time.sleep(1)
    start_time = time.time()
    await bot.send_document(ka, caption=cc1)
    count+=1
    await reply.delete (True)
    time.sleep(1)
    os.remove(ka)
    time.sleep(3) 


def decrypt_file(file_path, key):  
    if not os.path.exists(file_path): 
        return False  

    with open(file_path, "r+b") as f:  
        num_bytes = min(28, os.path.getsize(file_path))  
        with mmap.mmap(f.fileno(), length=num_bytes, access=mmap.ACCESS_WRITE) as mmapped_file:  
            for i in range(num_bytes):  
                mmapped_file[i] ^= ord(key[i]) if i < len(key) else i 
    return True  

async def download_and_decrypt_video(url, cmd, name, key):  
    video_path = await download_video(url, cmd, name)  
    
    if video_path:  
        decrypted = decrypt_file(video_path, key)  
        if decrypted:  
            print(f"File {video_path} decrypted successfully.")  
            return video_path  
        else:  
            print(f"Failed to decrypt {video_path}.")  
            return None  

async def send_vid(bot: Client, m: Message, cc, filename, thumb, name, prog, channel_id):
    print(f"[INFO] Starting send_vid for filename: {filename}, thumb: {thumb}, name: {name}")
    try:
        # Get absolute path for thumbnail
        thumbnail_path = os.path.join(os.getcwd(), f"{filename}.jpg")
        print(f"[INFO] Thumbnail path: {thumbnail_path}")

        # Step 1: Generate thumbnail using FFmpeg
        print("[INFO] Generating thumbnail")
        result = subprocess.run(
            f'ffmpeg -i "{filename}" -ss 00:00:10 -vframes 1 -q:v 2 -s 640x360 "{thumbnail_path}"',
            shell=True,
            capture_output=True,
            text=True
        )
        print(f"[FFmpeg] stdout: {result.stdout}")
        print(f"[FFmpeg] stderr: {result.stderr}")
        if result.returncode != 0:
            print(f"[ERROR] FFmpeg failed with code {result.returncode}")
            await m.reply_text(f"FFmpeg error: {result.stderr}")
            return

        # Verify thumbnail file exists
        if not os.path.exists(thumbnail_path):
            print(f"[ERROR] Thumbnail {thumbnail_path} not generated")
            await m.reply_text(f"Error: Thumbnail not generated")
            return
        print(f"[INFO] Thumbnail generated: {thumbnail_path}")

        # Step 2: Add watermark using Pillow
        print("[INFO] Adding watermark")
        try:
            image = Image.open(thumbnail_path).convert("RGBA")
            draw = ImageDraw.Draw(image)
            width, height = image.size
            print(f"[INFO] Image size: {width}x{height}")

            # Load font
            try:
                font = ImageFont.truetype("arial.ttf", size=height // 10)
                print("[INFO] Using arial.ttf font")
            except:
                font = ImageFont.load_default()
                print("[WARNING] Falling back to default font")

            text = "THUNDER HAXOL"
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x = (width - text_width) / 2
            y = (height - text_height) / 2
            print(f"[INFO] Text position: ({x}, {y})")

            # Add shadow and text
            draw.text((x + 5, y + 5), text, fill=(50, 50, 50, 180), font=font)
            draw.text((x, y), text, fill=(0, 0, 0, 204), font=font)

            # Save image
            image.convert("RGB").save(thumbnail_path, quality=95)
            print(f"[INFO] Watermarked thumbnail saved: {thumbnail_path}")

        except Exception as e:
            print(f"[ERROR] Watermarking failed: {str(e)}")
            await m.reply_text(f"Watermarking failed: {str(e)}")
            return

        # Step 3: Force use of watermarked thumbnail
        print(f"[INFO] Thumb parameter: {thumb}")
        thumbnail = thumbnail_path
        print(f"[INFO] Forcing thumbnail: {thumbnail}")

        # Step 4: Upload to Telegram
        await prog.delete(True)
        reply1 = await bot.send_message(channel_id, f"**📩 Uploading Video 📩:-**\n<blockquote>**{name}**</blockquote>")
        reply = await m.reply_text(f"**Generate Thumbnail:**\n<blockquote>**{name}**</blockquote>")

        dur = int(duration(filename))  # Assuming duration() is defined
        start_time = time.time()

        try:
            print("[INFO] Uploading video with thumbnail")
            await bot.send_video(
                channel_id,
                filename,
                caption=cc,
                supports_streaming=True,
                height=720,
                width=1280,
                thumb=thumbnail,
                duration=dur,
                progress=progress_bar,  # Assuming progress_bar is defined
                progress_args=(reply, start_time)
            )
            print("[INFO] Video uploaded successfully")
        except Exception as e:
            print(f"[WARNING] Video upload failed: {str(e)}")
            await bot.send_document(
                channel_id,
                filename,
                caption=cc,
                progress=progress_bar,
                progress_args=(reply, start_time)
            )
            print("[INFO] Document uploaded successfully")

        # Cleanup
        print("[INFO] Cleaning up files")
        if os.path.exists(filename):
            os.remove(filename)
        if os.path.exists(thumbnail_path):
            os.remove(thumbnail_path)
        await reply.delete(True)
        await reply1.delete(True)

    except Exception as e:
        print(f"[ERROR] Unexpected error: {str(e)}")
        await m.reply_text(f"Error: {str(e)}")

async def send_vyyid(bot: Client, m: Message, cc, filename, thumb, name, prog, channel_id):
    try:
        # Step 1: Generate thumbnail using FFmpeg
        logger.info(f"Generating thumbnail for {filename}")
        result = subprocess.run(
            f'ffmpeg -i "{filename}" -ss 00:00:10 -vframes 1 -q:v 2 "{filename}.jpg"',
            shell=True,
            capture_output=True,
            text=True,
            check=True
        )
        logger.info(f"FFmpeg output: {result.stdout}")

        # Verify thumbnail file exists
        if not os.path.exists(f"{filename}.jpg"):
            logger.error(f"Thumbnail {filename}.jpg not generated")
            await m.reply_text(f"Error: Thumbnail {filename}.jpg not generated")
            return

        # Step 2: Add watermark using Pillow
        logger.info(f"Adding watermark to {filename}.jpg")
        try:
            # Open image in RGBA mode for transparency
            image = Image.open(f"{filename}.jpg").convert("RGBA")
            draw = ImageDraw.Draw(image)
            width, height = image.size

            # Load a font (try system font or fallback to default)
            try:
                # Use a bold system font or downloaded TTF (e.g., from Google Fonts)
                font = ImageFont.truetype("arial.ttf", size=height // 12)  # Larger font for visibility
                logger.info("Using arial.ttf font")
            except:
                font = ImageFont.load_default(size=height // 12)
                logger.warning("Falling back to default font")

            text = "THUNDER HAXOL"
            # Get text bounding box for centering
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x = (width - text_width) / 2
            y = (height - text_height) / 2

            # Add shadow for better visibility
            draw.text((x + 5, y + 5), text, fill=(50, 50, 50, 180), font=font)
            # Draw main text: Black color with 80% opacity
            draw.text((x, y), text, fill=(0, 0, 0, 204), font=font)

            # Save the modified image as JPEG
            image.convert("RGB").save(f"{filename}.jpg", quality=95)
            logger.info(f"Watermarked thumbnail saved as {filename}.jpg")

        except Exception as e:
            logger.error(f"Watermarking failed: {str(e)}")
            await m.reply_text(f"Watermarking failed: {str(e)}")
            return

        # Step 3: Original logic for thumbnail selection and upload
        await prog.delete(True)
        reply1 = await bot.send_message(channel_id, f"**📩 Uploading Video 📩:-**\n<blockquote>**{name}**</blockquote>")
        reply = await m.reply_text(f"**Generate Thumbnail:**\n<blockquote>**{name}**</blockquote>")

        # Log thumb value for debugging
        logger.info(f"Thumb value: {thumb}")
        try:
            if thumb == "/d":
                thumbnail = f"{filename}.jpg"
                logger.info(f"Using generated thumbnail: {thumbnail}")
            else:
                thumbnail = thumb
                logger.info(f"Using custom thumbnail: {thumbnail}")

        except Exception as e:
            logger.error(f"Thumbnail selection error: {str(e)}")
            await m.reply_text(str(e))
            return

        dur = int(duration(filename))  # Assuming duration() is defined elsewhere
        start_time = time.time()

        try:
            await bot.send_video(
                channel_id,
                filename,
                caption=cc,
                supports_streaming=True,
                height=720,
                width=1280,
                thumb=thumbnail,
                duration=dur,
                progress=progress_bar,  # Assuming progress_bar is defined
                progress_args=(reply, start_time)
            )
            logger.info("Video uploaded successfully")
        except Exception as e:
            logger.warning(f"Video upload failed, trying document: {str(e)}")
            await bot.send_document(
                channel_id,
                filename,
                caption=cc,
                progress=progress_bar,
                progress_args=(reply, start_time)
            )
            logger.info("Document uploaded successfully")

        # Cleanup
        os.remove(filename)
        await reply.delete(True)
        await reply1.delete(True)
        if os.path.exists(f"{filename}.jpg"):
            os.remove(f"{filename}.jpg")
            logger.info(f"Removed thumbnail: {filename}.jpg")

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        await m.reply_text(f"Error: {str(e)}")
        

async def send_viid(bot: Client, m: Message, cc, filename, thumb, name, prog, channel_id):
    #subprocess.run(f'ffmpeg -i "{filename}" -ss 00:00:10 -vframes 1 "{filename}.jpg"', shell=True)
    subprocess.run(
        f'ffmpeg -i "{filename}" -ss 00:00:10 -vframes 1 -q:v 2 '
        f'-vf "drawtext=text=\'THUNDER HAXOL\':fontcolor=black@0.8:fontsize=h/15:'
        f'x=(w-tw)/2:y=(h-th)/2" '
        f'"{filename}.jpg"',
        shell=True
    )
    await prog.delete (True)
    reply1 = await bot.send_message(channel_id, f"**📩 Uploading Video 📩:-**\n<blockquote>**{name}**</blockquote>")
    reply = await m.reply_text(f"**Generate Thumbnail:**\n<blockquote>**{name}**</blockquote>")
    try:
        if thumb == "/d":
            thumbnail = f"{filename}.jpg"
        else:
            thumbnail = thumb
            
    except Exception as e:
        await m.reply_text(str(e))
      
    dur = int(duration(filename))
    start_time = time.time()

    try:
        await bot.send_video(channel_id, filename, caption=cc, supports_streaming=True, height=720, width=1280, thumb=thumbnail, duration=dur, progress=progress_bar, progress_args=(reply, start_time))
    except Exception:
        await bot.send_document(channel_id, filename, caption=cc, progress=progress_bar, progress_args=(reply, start_time))
    os.remove(filename)
    await reply.delete(True)
    await reply1.delete(True)
    os.remove(f"{filename}.jpg")

async def send_vvid(bot: Client, m: Message, cc, filename, thumb, name, prog, channel_id):
    try:
        # Step 1: Generate thumbnail using FFmpeg
        logger.info(f"Generating thumbnail for {filename}")
        subprocess.run(
            f'ffmpeg -i "{filename}" -ss 00:00:10 -vframes 1 -q:v 2 "{filename}.jpg"',
            shell=True,
            check=True  # Raise error if FFmpeg fails
        )

        # Verify thumbnail file exists
        if not os.path.exists(f"{filename}.jpg"):
            logger.error(f"Thumbnail {filename}.jpg not generated")
            await m.reply_text(f"Error: Thumbnail {filename}.jpg not generated")
            return

        # Step 2: Add watermark using Pillow
        logger.info(f"Adding watermark to {filename}.jpg")
        try:
            image = Image.open(f"{filename}.jpg").convert("RGBA")
            draw = ImageDraw.Draw(image)
            width, height = image.size

            # Load a stylish font
            try:
                font = ImageFont.truetype("arial.ttf", size=height // 15)
                logger.info("Using arial.ttf font")
            except:
                font = ImageFont.load_default()
                logger.warning("Falling back to default font")

            text = "THUNDER HAXOL"
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x = (width - text_width) / 2
            y = (height - text_height) / 2

            # Draw text: Black color with 80% opacity
            draw.text((x, y), text, fill=(0, 0, 0, 204), font=font)

            # Save the modified image
            image.convert("RGB").save(f"{filename}.jpg", quality=95)
            logger.info(f"Watermarked thumbnail saved as {filename}.jpg")

        except Exception as e:
            logger.error(f"Watermarking failed: {str(e)}")
            await m.reply_text(f"Watermarking failed: {str(e)}")
            return

        # Step 3: Original logic
        await prog.delete(True)
        reply1 = await bot.send_message(channel_id, f"**📩 Uploading Video 📩:-**\n<blockquote>**{name}**</blockquote>")
        reply = await m.reply_text(f"**Generate Thumbnail:**\n<blockquote>**{name}**</blockquote>")

        # Log thumb value for debugging
        logger.info(f"Thumb value: {thumb}")
        try:
            if thumb == "/d":
                thumbnail = f"{filename}.jpg"
                logger.info(f"Using generated thumbnail: {thumbnail}")
            else:
                thumbnail = thumb
                logger.info(f"Using custom thumbnail: {thumbnail}")

        except Exception as e:
            logger.error(f"Thumbnail selection error: {str(e)}")
            await m.reply_text(str(e))
            return

        dur = int(duration(filename))
        start_time = time.time()

        try:
            await bot.send_video(
                channel_id,
                filename,
                caption=cc,
                supports_streaming=True,
                height=720,
                width=1280,
                thumb=thumbnail,
                duration=dur,
                progress=progress_bar,
                progress_args=(reply, start_time)
            )
            logger.info("Video uploaded successfully")
        except Exception as e:
            logger.warning(f"Video upload failed, trying document: {str(e)}")
            await bot.send_document(
                channel_id,
                filename,
                caption=cc,
                progress=progress_bar,
                progress_args=(reply, start_time)
            )
            logger.info("Document uploaded successfully")

        # Cleanup
        os.remove(filename)
        await reply.delete(True)
        await reply1.delete(True)
        if os.path.exists(f"{filename}.jpg"):
            os.remove(f"{filename}.jpg")
            logger.info(f"Removed thumbnail: {filename}.jpg")

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        await m.reply_text(f"Error: {str(e)}")
