import time
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import requests

# ================= 사용자 설정 구간 =================
BASE_URL_PATTERN = "https://www.nyj.go.kr/rent/rent/application/index/{year}/{month}/29/2/NYJ07/02/{place_id}"

TARGET_PLACES = [
    {"name": "별내동 유소년 풋살장", "id": "29"},
    {"name": "일반 풋살구장",       "id": "13"}
]

# 공백 없이 붙여 쓴 타겟 시간 (정확히 이것만 찾습니다)
TARGET_TIME_CLEAN = "08:00~10:00"

TELEGRAM_TOKEN = "TELEGRAM_TOKEN"
TELEGRAM_CHAT_ID = "TELEGRAM_CHAT_ID"
# =================================================

def send_telegram_msg(message):
    """텔레그램으로 알림을 보내는 함수"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"텔레그램 전송 실패: {e}")

def check_all_reservations():
    options = webdriver.ChromeOptions()
    
    # --- GitHub Actions 환경을 위한 필수 옵션 추가 ---
    options.add_argument('--headless') # 창 없이 실행
    options.add_argument('--no-sandbox') # 보안 기능 해제 (리눅스 환경 필수)
    options.add_argument('--disable-dev-shm-usage') # 공유 메모리 부족 방지
    options.add_argument('--disable-gpu') # GPU 가속 비활성화
    # ----------------------------------------------
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    print(f"🚀 정밀 예약 확인({TARGET_TIME_CLEAN})을 시작합니다...\n")
    
    try:
        # 날짜 계산 (25일 이후면 다음 달)
        today = datetime.now()
        if today.day > 25:
            if today.month == 12:
                target_year = str(today.year + 1)
                target_month = "01"
            else:
                target_year = str(today.year)
                target_month = str(today.month + 1).zfill(2)
        else:
            target_year = str(today.year)
            target_month = str(today.month).zfill(2)

        print(f"📅 검색 대상: {target_year}년 {target_month}월")
        print("="*60)

        for place in TARGET_PLACES:
            place_name = place["name"]
            place_id = place["id"]
            
            final_url = BASE_URL_PATTERN.format(year=target_year, month=target_month, place_id=place_id)
            
            print(f"\n🏟️ [구장] {place_name} (ID: {place_id})")
            driver.get(final_url)
            time.sleep(2) 
            
            rows = driver.find_elements(By.CSS_SELECTOR, "table.rent_daylist_table_sports tbody tr")
            
            current_date_str = ""
            found_count = 0
            
            for row in rows:
                # [업그레이드] 텍스트 전체가 아니라, 칸(td)별로 쪼개서 분석합니다.
                tds = row.find_elements(By.TAG_NAME, "td")
                
                # 데이터가 없는 줄은 패스
                if not tds: continue

                # -------------------------------------------------
                # 1. 날짜 칸 확인 (Rowspan 처리)
                # -------------------------------------------------
                # 칸 개수가 6개면: [날짜, 회차, 시간, 행사명, 단체명, 버튼] -> 날짜가 있는 줄
                # 칸 개수가 5개면: [회차, 시간, 행사명, 단체명, 버튼]       -> 날짜가 없는 줄
                
                if len(tds) == 6:
                    date_text = tds[0].text.strip() # 날짜 추출
                    if f"{target_year}-" in date_text:
                        current_date_str = date_text.split("\n")[0]
                    
                    # 날짜가 있는 줄은 시간/단체명 인덱스가 밀림
                    idx_time = 2
                    idx_team = 4
                else:
                    # 날짜가 없는 줄
                    idx_time = 1
                    idx_team = 3
                
                # -------------------------------------------------
                # 2. 시간 정확히 비교
                # -------------------------------------------------
                time_text = tds[idx_time].text.replace(" ", "") # 공백제거 "08:00~10:00"
                
                # "일요일"이면서 + 시간이 "08:00~10:00"과 정확히 일치하는가?
                if "(일)" in current_date_str and time_text == TARGET_TIME_CLEAN:
                    found_count += 1
                    
                    # 예약자명 가져오기
                    team_name = tds[idx_team].text.strip()
                    if not team_name:
                        team_name = "(없음)"
                    
                    print(f"   ▶ 발견: {current_date_str} / 예약자: {team_name}")
                    
                    # -------------------------------------------------
                    # 3. 예약 버튼(이미지) 상태 확인
                    # -------------------------------------------------
                    try:
                        imgs = row.find_elements(By.TAG_NAME, "img")
                        status_msg = "상태 미확인"
                        
                        for img in imgs:
                            alt = img.get_attribute("alt")
                            if alt == "예약가능":
                                # print(f"      🎉 [대박] 예약 가능!! (빈자리) -> {final_url}")
                                # status_msg = "가능"
                                # break
                                msg = f"🎉 [알림]\n{place_name} 빈자리 발견!\n날짜: {current_date_str}\n링크: {final_url}"
                                print(f"      {msg}")
                                send_telegram_msg(msg) # 알림 발송!
                                status_msg = "가능"
                                break
                            elif alt == "예약완료":
                                print(f"      😭 [마감] 예약 완료됨")
                                status_msg = "마감"
                                break
                        
                        if status_msg == "상태 미확인":
                             # 이미지가 없는데 텍스트가 비어있으면 보통 '마감'이나 '준비중'
                             print("      🔒 [잠김] 예약 불가 (버튼 없음)")
                                
                    except Exception as e:
                        print(f"      ⚠️ 에러: {e}")
            
            if found_count == 0:
                print(f"   ⚠️ '{TARGET_TIME_CLEAN}' 시간대(일요일) 데이터가 없습니다.")
            
            print("-" * 60)
            time.sleep(1)

    except Exception as e:
        print(f"💥 오류 발생: {e}")
        
    finally:
        print("\n🛑 종료합니다.")
        # driver.quit()

if __name__ == "__main__":
    # 1. 예약 확인 실행
    check_all_reservations()
    
    # 2. [추가] 자정 안부 메시지 로직
    # GitHub Actions 서버는 UTC 기준이므로 한국 시간(KST)으로 변환하여 체크합니다.
    from datetime import timedelta
    
    now_utc = datetime.utcnow()
    now_kst = now_utc + timedelta(hours=9) # UTC -> KST 변환
    
    # 00:00 ~ 00:15 사이에 실행될 때 한 번만 메시지 전송
    # 10분 주기이므로 이 범위 안에 반드시 한 번 걸립니다.
    if now_kst.hour == 0 and 0 <= now_kst.minute < 15:
        report_msg = f"🌅 [생존 신고] {now_kst.strftime('%Y-%m-%d')} 자정입니다.\n봇이 정상적으로 작동 중이며 10분마다 감시 중입니다."
        send_telegram_msg(report_msg)

