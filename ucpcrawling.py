from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from pymongo import MongoClient
import requests
import certifi
import random
import time
import re

# ==========================================
# 1. KONEKSI MONGODB
# ==========================================
# Pastikan Anda sudah melakukan Drop Collection di MongoDB Anda sebelum menjalankan ini
client = MongoClient('mongodb+srv://Praktikum1Cloud:PawAnakBaik123@prakcloud.hpxi581.mongodb.net/')
collections = client['ucp1']['CNBCIndo']

def crawl_cnbc_hybrid_final():
    print("🤖 Mempersiapkan Robot Browser (Selenium)...")
    
    # Konfigurasi Chrome Headless (berjalan di background)
    chrome_options = Options()
    chrome_options.add_argument('--headless=new') 
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--log-level=3') 
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    # URL Pencarian
    search_url = 'https://www.cnbcindonesia.com/search?query=Environmental+Sustainability'
    headers_requests = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    print("\n--- Memulai Proses Crawling ---")
    print(f'📄 [SELENIUM] Membuka Halaman Pencarian...')
    driver.get(search_url)
    
    print("⏳ Menunggu halaman dimuat...")
    time.sleep(5) 

    # ==========================================
    # LOGIKA SCROLLING OTOMATIS
    # ==========================================
    jumlah_scroll = 3 # Naikkan angka ini jika ingin mengambil data yang lebih lawas
    
    for i in range(jumlah_scroll):
        print(f"⬇️ Melakukan scroll ke bawah ({i+1}/{jumlah_scroll}) untuk memuat artikel...")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(4) 

    # Ambil HTML setelah di-scroll penuh
    html_matang = driver.page_source
    soup = BeautifulSoup(html_matang, 'html.parser')
    
    all_links = soup.find_all('a', href=True)
    list_url_berita = []

    # Filter khusus untuk URL berita CNBC
    for a in all_links:
        href = a['href']
        if "cnbcindonesia.com" in href and re.search(r'\d{8,}', href):
            if href not in list_url_berita:
                list_url_berita.append(href)

    driver.quit() # Robot Chrome ditutup karena link sudah di tangan

    if not list_url_berita:
        print('❌ Tidak ada link artikel ditemukan. Coba cek kembali koneksi internet atau ubah keyword.')
        return

    print(f"🔍 Ditemukan TOTAL {len(list_url_berita)} link artikel. Memulai ekstraksi isi (Requests)...")

    # ==========================================
    # EKSTRAKSI ISI BERITA (REQUESTS)
    # ==========================================
    sukses_tersimpan = 0

    for url in list_url_berita:
        try:
            # Cek Database
            if collections.find_one({'url': url}):
                print(f"⏩ Dilewati (Sudah ada di DB): {url}")
                continue

            isi_res = requests.get(url, headers=headers_requests, timeout=15)
            isi_soup = BeautifulSoup(isi_res.text, 'html.parser')

            # 1. Judul
            judul_tag = isi_soup.find('h1')
            judul = judul_tag.text.strip() if judul_tag else 'Judul tidak ditemukan'

            # 2. Author (Prioritas Meta Tag)
            author_meta = isi_soup.find('meta', attrs={'name': 'author'}) or isi_soup.find('meta', attrs={'name': 'dtk:author'})
            if author_meta and author_meta.get('content'):
                author = author_meta['content'].strip()
            else:
                author_tag = isi_soup.find('div', class_='author') or isi_soup.find('span', class_='author')
                author = author_tag.text.strip() if author_tag else 'Author tidak ditemukan'

            # 3. Tanggal (Prioritas Meta Tag)
            tanggal_meta = isi_soup.find('meta', attrs={'name': 'dtk:publishdate'}) or isi_soup.find('meta', attrs={'property': 'article:published_time'})
            if tanggal_meta and tanggal_meta.get('content'):
                tanggal = tanggal_meta['content'].strip()
            else:
                tanggal_tag = isi_soup.find('div', class_='date') or isi_soup.find('time')
                tanggal = tanggal_tag.text.strip() if tanggal_tag else 'Tanggal tidak ditemukan'

            # 4. Tags
            tags_meta = isi_soup.find('meta', attrs={'name': 'keywords'})
            tags = tags_meta['content'].strip() if tags_meta else 'Tag tidak ditemukan'

            # 5. Thumbnail
            thumbnail_meta = isi_soup.find('meta', attrs={'property': 'og:image'})
            thumbnail = thumbnail_meta['content'].strip() if thumbnail_meta else 'Thumbnail tidak ditemukan'

            # 6. Isi Berita (Pembersihan Lanjutan & Strategi 3 Lapis)
            body_content = isi_soup.find('div', class_='detail_text') or isi_soup.find('div', class_='detail-text')
            
            # Jika bukan artikel reguler, coba cari wadah artikel video/foto
            if not body_content:
                body_content = isi_soup.find('div', class_='artikel-video') or isi_soup.find('article')

            isi_berita = 'Isi tidak ditemukan'
            
            if body_content:
                # Bersihkan elemen iklan, tabel, atau video iframe
                for elemen_kotor in body_content.find_all(['script', 'style', 'table', 'div', 'iframe']):
                    elemen_kotor.decompose()
                    
                # Lapis 1: Coba ambil dari tag <p>
                isi_paragraf_list = [p.get_text(strip=True) for p in body_content.find_all('p') if p.get_text(strip=True)]
                
                if isi_paragraf_list:
                    isi_berita = ' '.join(isi_paragraf_list)
                else:
                    # Lapis 2: Jika tidak ada <p>, ambil seluruh teks mentah yang tersisa
                    teks_mentah = body_content.get_text(separator=' ', strip=True)
                    if teks_mentah:
                        isi_berita = teks_mentah
            
            # Lapis 3: Jika masih kosong (misal khusus video tanpa teks), ambil Meta Description
            if isi_berita == 'Isi tidak ditemukan' or len(isi_berita) < 20:
                desc_meta = isi_soup.find('meta', attrs={'name': 'description'})
                if desc_meta and desc_meta.get('content'):
                    isi_berita = "(Ringkasan) " + desc_meta['content'].strip()

            # Menyusun Data
            data_final = {
                'url': url,
                'judul': judul,
                'tanggal_publish': tanggal,
                'author': author,
                'tag_kategori': tags,
                'isi_berita': isi_berita,
                'thumbnail': thumbnail
            }

            # Memasukkan ke DB
            collections.insert_one(data_final)
            print(f'✅ Tersimpan: {judul[:60]}...')
            sukses_tersimpan += 1

            # Jeda agar tidak terkena blokir
            time.sleep(random.uniform(1.0, 2.5)) 

        except Exception as e:
            print(f'❌ Error pada saat ekstrak {url}: {e}')

    print(f"\n--- Crawling Selesai! Berhasil menyimpan {sukses_tersimpan} artikel baru. ---")

if __name__ == "__main__":
    crawl_cnbc_hybrid_final()