# -*- coding: utf-8 -*-
"""
지역 + 키워드 + 개수를 입력받아 홍보글(.txt)을 Claude API로 새로 써요.
만든 글은 '네이버자동발행 / [지역] [키워드] 글'  폴더에 저장되고,
원하면 naver_autopost.py 의 POSTS_DIR 를 그 폴더로 바꿔줘요.

    py gen_posts.py
"""
import os
import re
import sys
import json
import random
from pathlib import Path

import anthropic

# =====================================================================
#  설정
# =====================================================================
MODEL = "claude-opus-5-5"     # 더 싸게: "claude-sonnet-5-5" (품질 약간 낮음, 비용 절반)
EFFORT = "low"                # 글쓰기라 low 로 충분 (비용 절약)
BUSINESS = "토일케어"          # 마지막 문단에 넣을 업체명 (실행할 때 py gen_posts.py 홈케어 처럼 바꿀 수 있어요)
NAMES = {"homecare": "홈케어", "toilcare": "토일케어"}   # bat 에서 영어로 넘겨서 한글 깨짐 방지
if len(sys.argv) > 1 and sys.argv[1].strip():
    BUSINESS = NAMES.get(sys.argv[1].strip().lower(), sys.argv[1].strip())
DEFAULT_SUFFIX = "및 막힘해결 업체 추천"
# =====================================================================

BASE = Path(__file__).resolve().parent
KEY_FILE = BASE / "API키.txt"
SAMPLE_FILE = BASE / "예시글.txt"
AUTOPOST = BASE / "naver_autopost.py"

# 글마다 다른 상황을 주려고 랜덤으로 섞어 쓰는 관점들
ANGLES = [
    "이사 직후 새 집", "혼자 사는 원룸·오피스텔", "아이가 있는 집", "어르신이 사는 집",
    "오래된 빌라·구축 아파트", "신축 아파트 입주 초기", "사무실·오피스 공용 화장실",
    "상가·식당 화장실", "학원·병원 등 다중이용시설", "명절·손님 방문 직후",
    "겨울철 한파", "장마철·여름철", "늦은 밤·주말 갑작스러운 막힘", "임대 주택 세입자",
    "셀프로 뚫다가 더 심해진 경우", "반복해서 자주 막히는 경우", "공사·리모델링 후",
    "카페·편의점 등 매장", "고층 아파트", "단독주택·다가구 주택",
]


def ask(prompt, default=""):
    v = input(prompt).strip()
    return v or default


def load_key():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return None  # SDK 가 환경변수에서 읽음
    if KEY_FILE.exists():
        k = KEY_FILE.read_text(encoding="utf-8-sig").strip().splitlines()
        if k and k[0].strip().startswith("sk-") and "여기에" not in k[0]:
            return k[0].strip()
    sys.exit(f"API 키가 없어요. {KEY_FILE.name} 파일 첫 줄에 sk-ant-... 키를 붙여넣고 저장하세요.")


def call(client, system, user, max_tokens=8000):
    resp = client.beta.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        output_config={"effort": EFFORT},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("모델이 작성을 거절했어요")
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def get_dongs(client, region):
    text = call(client,
                "너는 한국 행정구역 전문가야. 요청한 지역에 실제로 있는 동 이름만 JSON 배열로 답해. 다른 말은 쓰지 마.",
                f"'{region}'에 있는 동(행정동 또는 법정동) 이름을 모두 알려줘. "
                f"예: [\"당산동\", \"문래동\"]. 지역 이름은 빼고 동 이름만.",
                max_tokens=2000)
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return []
    try:
        names = json.loads(m.group())
    except json.JSONDecodeError:
        return []
    out = []
    for n in names:
        n = str(n).strip()
        if n and n not in out and len(n) <= 10:
            out.append(n)
    return out


SYSTEM = f"""너는 네이버 블로그 배관 업체 홍보글 작가야. 아래 규칙을 꼭 지켜.

형식
- 말투는 친근한 ~해요체.
- 한 문단은 한 문장(길어도 두 문장). 문단과 문단 사이에는 빈 줄 하나.
- 전체 문단 수 22~27개, 글자 수 공백 포함 1,300~1,800자.
- 소제목은 정확히 5개. 소제목은 마침표 없이 짧게(25자 이내) 한 줄로 쓰고 앞뒤에 빈 줄.
- 마크다운 기호(#, *, -, 번호 목록), 이모지, 따옴표 강조, 제목 줄은 쓰지 마. 본문만 써.
- 물결표(~)는 쓰지 마.

내용
- 첫 문단은 독자가 겪는 상황으로 자연스럽게 시작해.
- 키워드 문구를 본문에 정확히 그대로 3~4번 넣어: 도입부 1번, 중간 1~2번, 마지막 문단 1번.
- 지역 이름과 그 동네 특징(주거 형태, 상권, 건물 연식 등)을 자연스럽게 녹여. 확실하지 않은 사실은 지어내지 마.
- 증상 → 원인 → 직접 할 수 있는 응급 조치 → 전문 기술자의 점검·작업 → 작업 후 관리 흐름을 지키되, 소제목 문구와 문장은 매번 새롭게 써.
- 구체적인 금액, 전화번호, 할인, 과장 광고(최저가, 100% 등)는 쓰지 마. 비용은 '막힘 위치와 원인, 작업 방법에 따라 달라진다'는 식으로만.
- 마지막 문단에서 키워드 문구와 함께 '{BUSINESS}' 업체명을 한 번 자연스럽게 언급해.
"""


def write_post(client, region, dong, phrase, angle, sample):
    user = (f"키워드 문구: {phrase}\n"
            f"지역: {region} {dong}\n"
            f"이번 글의 상황/관점: {angle}\n\n"
            "아래 예시글은 형식과 말투만 참고하고, 문장·소제목·내용은 절대 따라 쓰지 마.\n"
            f"예시글에 나오는 업체명은 무시하고, 업체명은 반드시 '{BUSINESS}'만 써.\n"
            f"--- 예시글 ---\n{sample}\n--- 끝 ---")
    return call(client, SYSTEM, user)


def clean(text):
    text = text.replace("\r\n", "\n").replace("~", "∼")
    lines = []
    for line in text.split("\n"):
        line = re.sub(r"^\s*(#+|\*+|-|\d+\.)\s*", "", line).replace("**", "").strip()
        lines.append(line)
    blocks = [b.strip() for b in re.split(r"\n\s*\n", "\n".join(lines)) if b.strip()]
    return "\r\n\r\n".join(blocks) + "\r\n"


def check(text, phrase):
    problems = []
    n = text.count(phrase)
    if n < 3:
        problems.append(f"키워드 {n}번")
    if BUSINESS not in text:
        problems.append("업체명 없음")
    for other in NAMES.values():
        if other != BUSINESS and other in text.replace(BUSINESS, ""):
            problems.append(f"다른 업체명({other}) 들어감")
    if len(text) < 1000:
        problems.append("너무 짧음")
    return problems


def set_autopost_dir(folder):
    s = AUTOPOST.read_text(encoding="utf-8")
    s2 = re.sub(r'^POSTS_DIR = .*$', lambda m: f'POSTS_DIR = r"{folder}"', s, count=1, flags=re.M)
    AUTOPOST.write_text(s2, encoding="utf-8")


def main():
    print(f"=== 홍보글 자동 생성 (업체명: {BUSINESS}) ===\n")
    region = ask("지역 (예: 영등포구, 운정, 수원 영통구): ")
    if not region:
        sys.exit("지역을 입력해야 해요.")
    keyword = ask("키워드 (예: 변기뚫는비용, 세면대막힘 비용): ")
    if not keyword:
        sys.exit("키워드를 입력해야 해요.")
    suffix = ask(f"키워드 뒤 문구 [Enter = {DEFAULT_SUFFIX}]: ", DEFAULT_SUFFIX)
    try:
        count = int(ask("몇 개 만들까요? (숫자): ", "0"))
    except ValueError:
        count = 0
    if count <= 0:
        sys.exit("개수를 숫자로 입력해야 해요.")
    dong_in = ask("동 이름 직접 입력 (쉼표로 구분, Enter = 자동으로 찾기): ")

    key = load_key()
    client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()

    if dong_in:
        dongs = [d.strip() for d in re.split(r"[,，\s]+", dong_in) if d.strip()]
    else:
        print("\n동 목록 찾는 중...")
        dongs = get_dongs(client, region)
        if not dongs:
            sys.exit("동 목록을 못 찾았어요. 동 이름을 직접 입력해 주세요.")
        print(f"찾은 동 {len(dongs)}개: {', '.join(dongs)}")

    out_dir = BASE / (f"{region} {keyword} 글" if BUSINESS == "토일케어" else f"{region} {keyword} 글 ({BUSINESS})")
    out_dir.mkdir(exist_ok=True)
    exists = {p.stem for p in out_dir.glob("*.txt")}
    random.shuffle(dongs)
    todo = []
    for d in dongs:
        phrase = f"{region} {d} {keyword} {suffix}".strip()
        if phrase not in exists:
            todo.append((d, phrase))
    if len(todo) < count:
        print(f"※ 새로 쓸 수 있는 동이 {len(todo)}개뿐이라 {len(todo)}개만 만들어요.")
    todo = todo[:count]

    sample = SAMPLE_FILE.read_text(encoding="utf-8-sig") if SAMPLE_FILE.exists() else ""
    angles = random.sample(ANGLES, len(ANGLES))
    made = 0
    for i, (dong, phrase) in enumerate(todo):
        angle = angles[i % len(angles)]
        print(f"\n[{i + 1}/{len(todo)}] {phrase}  (관점: {angle})")
        text = ""
        for attempt in range(2):
            try:
                text = clean(write_post(client, region, dong, phrase, angle, sample))
            except anthropic.AuthenticationError:
                sys.exit("API 키가 잘못됐어요. API키.txt 를 확인하세요.")
            except anthropic.PermissionDeniedError:
                sys.exit("API 키 권한이 없어요. 콘솔에서 키를 확인하세요.")
            except anthropic.RateLimitError:
                print("  요청이 많아 잠시 막혔어요. 다시 시도해요...")
                continue
            except anthropic.APIStatusError as e:
                if "credit" in str(e).lower() or "billing" in str(e).lower():
                    sys.exit("API 크레딧이 부족해요. console.anthropic.com 에서 충전하세요.")
                print(f"  API 오류({e.status_code}), 다시 시도해요...")
                continue
            except anthropic.APIConnectionError:
                print("  인터넷 연결 오류, 다시 시도해요...")
                continue
            except RuntimeError as e:
                print(f"  {e}")
                continue
            problems = check(text, phrase)
            if not problems:
                break
            print(f"  다시 쓰는 중 ({', '.join(problems)})")
        if not text:
            print("  실패해서 건너뛰어요.")
            continue
        with open(out_dir / f"{phrase}.txt", "w", encoding="utf-8", newline="") as f:
            f.write(text)
        made += 1
        print(f"  저장 완료 ({len(text)}자)")

    print(f"\n완료: {made}개 → {out_dir}")
    if made and AUTOPOST.exists():
        if ask("\n자동발행 글 폴더(POSTS_DIR)를 이 폴더로 바꿀까요? (Y/n): ", "y").lower().startswith("y"):
            set_autopost_dir(str(out_dir))
            print("바꿨어요. 이제 3_미리보기.bat → 4_실행.bat 을 실행하면 돼요.")


if __name__ == "__main__":
    main()
