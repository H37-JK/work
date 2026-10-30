# -*- coding: utf-8 -*-
"""
네이버 블로그 자동 작성 (스마트에디터 ONE + Playwright)

사용법 (자세한 건 '사용가이드.txt' 참고)
    py naver_autopost.py login   -> 처음 한 번, 열린 크롬에서 직접 네이버 로그인
    py naver_autopost.py test    -> 브라우저 없이 글/사진 매칭만 미리 확인
    py naver_autopost.py run     -> 실제 작성 (임시저장 또는 발행)
"""
import sys
import re
import random
import time
import shutil
import datetime
from pathlib import Path

# =====================================================================
#  설정 (메모장으로 열어서 이 부분만 고치면 돼요)
# =====================================================================

# 내 블로그 아이디 (blog.naver.com/여기부분)
BLOG_ID = "these9907"

# 글(.txt) 폴더. 파일명 = 제목(키워드)
POSTS_DIR = r"C:\Users\these\Desktop\네이버자동발행\운정 싱크대 글"

# 사진 폴더. 글마다 이 폴더(하위 폴더 포함)에서 IMAGES_PER_POST장을 랜덤으로 골라요.
# 사진은 옮기지 않고 다른 글에서도 다시 쓸 수 있어요 (한 글 안에서는 중복 없음).
IMAGES_DIR = r"C:\Users\these\Desktop\네이버자동발행\작업"
IMAGES_PER_POST = 10

# 제목에 이 단어가 있으면 작업 폴더 안의 해당 하위 폴더에서만 사진을 골라요.
# (위에서부터 먼저 맞는 단어 기준. 단어가 없거나 폴더가 없거나 비어 있으면 작업 폴더 전체에서 골라요)
IMAGE_FOLDERS = {
    "변기": "변기",
    "세면대": "세면대",
    "싱크대": "싱크대",
    "수전": "수전",
}

# 매 글마다 항상 넣는 고정 사진 (작업 폴더 안의 파일명). 사용완료로 옮기지 않아요.
# 안 쓰려면 FIXED_IMAGE = ""
FIXED_IMAGE = "1.png"
FIXED_IMAGE_POSITION = "맨앞"   # "맨앞" = 본문 시작(항상 첫 사진), "맨끝" = 본문 마지막

# 추가 고정 사진 (작업 폴더 안 파일명). TOP = 고정 사진 바로 다음, END = 본문 맨 마지막
# 예) TOP_IMAGES = ["2.png"], END_IMAGES = ["2.png"]   (7번은 이렇게 자동 설정돼요)
TOP_IMAGES = []
END_IMAGES = []

# "임시저장" 또는 "발행"  (처음엔 꼭 임시저장으로 확인하세요)
MODE = "발행"

# 하루 최대 개수 / 한 번 실행에 최대 개수 (0 = 제한 없음, 폴더의 글 전부 작성)
MAX_PER_DAY = 0
MAX_PER_RUN = 0

# 글과 글 사이 대기 시간 (분, 랜덤). (0, 0) = 대기 없이 바로 다음 글
WAIT_MINUTES = (0, 0)

# 사진 위치: "분산" = 문단 사이사이에 고르게,  "맨끝" = 본문 끝에 모아서
IMAGE_POSITION = "분산"

# 소제목(마침표 없는 짧은 줄)을 굵게 (툴바 굵게 버튼 사용)
BOLD_SUBHEADINGS = True

# 물결표(~)를 비슷한 모양의 ∼ 로 바꿔서 입력 (에디터가 ~글자~ 를 취소선으로 바꾸는 것 방지)
FIX_TILDE = True

# 발행할 때 태그 자동 입력 (제목의 지역/키워드에서 뽑음). 추가 태그는 여기에
ADD_TAGS = True
EXTRA_TAGS = ["토일케어"]

# 입력 방식: True = 문장을 한 번에 입력 (빠름), False = 한 글자씩 타이핑 (느림)
FAST_INPUT = True
TYPE_DELAY_MS = (15, 45)   # FAST_INPUT = False 일 때 글자당 ms

# =====================================================================

BASE = Path(__file__).resolve().parent
PROFILE_DIR = BASE / "chrome_profile"      # 로그인 정보가 저장되는 크롬 프로필
LOG_FILE = BASE / "완료목록.txt"            # 처리한 글 기록 (다시 안 올림)
ERR_DIR = BASE / "오류스크린샷"
CHECK_DIR = BASE / "확인스크린샷"            # 글마다 저장 직전 화면
IMG_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


# ---------------------------------------------------------------- 공통
def log(msg):
    print(f"[{datetime.datetime.now():%H:%M:%S}] {msg}", flush=True)


def read_text(path):
    for enc in ("utf-8-sig", "cp949"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"글 파일 인코딩을 읽을 수 없어요: {path.name}")


def parse_post(path):
    """빈 줄로 문단을 나눠요. [('sub'|'para', 텍스트), ...]"""
    text = read_text(path).replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    out = []
    for b in blocks:
        is_sub = ("\n" not in b and len(b) <= 40
                  and not re.search(r"[.!?~…)\]\"'”’]$|[요다죠]$", b))
        out.append(("sub" if is_sub else "para", b))
    return out


def number_key(p):
    m = re.match(r"\d+", p.stem)
    return (0, int(m.group()), p.name) if m else (1, 0, p.name)


def list_images(d=None):
    d = Path(d or IMAGES_DIR)
    fixed = {n.lower() for n in [FIXED_IMAGE, *TOP_IMAGES, *END_IMAGES] if n}
    return sorted([p for p in d.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXT
                   and p.name.lower() not in fixed],
                  key=number_key)


def images_for(title, all_imgs):
    """제목에 맞는 하위 폴더 사진 목록과 폴더 이름. 없으면 전체."""
    for word, folder in IMAGE_FOLDERS.items():
        if word in title:
            sub = Path(IMAGES_DIR) / folder
            if sub.is_dir():
                imgs = list_images(sub)
                if imgs:
                    return imgs, folder
            return all_imgs, f"전체 ({folder} 폴더가 없거나 비어 있음)"
    return all_imgs, "전체"


def named_images(names):
    out = []
    for n in names:
        p = Path(IMAGES_DIR) / n
        if not p.exists():
            raise RuntimeError(f"고정 사진이 없어요: {p}")
        out.append(p)
    return out


def fixed_image():
    if not FIXED_IMAGE:
        return None
    p = Path(IMAGES_DIR) / FIXED_IMAGE
    if not p.exists():
        raise RuntimeError(f"고정 사진이 없어요: {p}")
    return p


def done_records():
    if not LOG_FILE.exists():
        return []
    rows = []
    for line in LOG_FILE.read_text(encoding="utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            rows.append(parts)
    return rows


def done_titles():
    return {r[2] for r in done_records()}


def today_count():
    today = datetime.date.today().isoformat()
    return sum(1 for r in done_records() if r[0].startswith(today))


def write_done(title, mode):
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M}\t{mode}\t{title}\n")


def pending_posts():
    done = done_titles()
    files = sorted(Path(POSTS_DIR).glob("*.txt"), key=lambda p: p.name)
    return [p for p in files if p.stem not in done]


def image_slots(n_blocks, n_images):
    """각 사진을 몇 번째 문단 뒤에 넣을지 (0부터)"""
    if IMAGE_POSITION == "맨끝" or n_blocks == 0:
        return [n_blocks - 1] * n_images
    return [max(0, round((i + 1) * n_blocks / (n_images + 1)) - 1) for i in range(n_images)]


def make_tags(title):
    words = re.sub(r"[^\w\s]", " ", title).split()
    tags = []
    for w in words:
        if w in ("및", "업체", "추천") or len(w) < 2:
            continue
        tags.append(w)
    # 지역+키워드 붙인 형태도 하나
    if len(words) >= 3:
        tags.append(words[0] + words[1])
        tags.append(words[1] + words[2])
    tags += EXTRA_TAGS
    seen, out = set(), []
    for t in tags:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out[:10]


# ---------------------------------------------------------------- 브라우저
def open_browser(p):
    PROFILE_DIR.mkdir(exist_ok=True)
    kw = dict(
        user_data_dir=str(PROFILE_DIR),
        headless=False,
        no_viewport=True,
        args=["--start-maximized", "--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    try:
        return p.chromium.launch_persistent_context(channel="chrome", **kw)  # 설치된 크롬
    except Exception:
        return p.chromium.launch_persistent_context(**kw)  # 없으면 playwright 크로미움


def human_pause(a=0.4, b=1.2):
    time.sleep(random.uniform(a, b))


def type_text(page, text):
    if FIX_TILDE:
        text = text.replace("~", "\u223c")
    if FAST_INPUT:
        page.keyboard.insert_text(text)
        time.sleep(0.15)
    else:
        page.keyboard.type(text, delay=random.randint(*TYPE_DELAY_MS))


# 툴바 서식 버튼 (굵게/기울임/밑줄/취소선)
FMT_BTN = {
    "bold": "button.se-bold-toolbar-button, button[data-name='bold']",
    "italic": "button.se-italic-toolbar-button, button[data-name='italic']",
    "underline": "button.se-underline-toolbar-button, button[data-name='underline']",
    "strike": "button.se-strikethrough-toolbar-button, button[data-name='strikethrough'], button[class*='strikethrough']",
}


def fmt_on(frame, name):
    try:
        btn = frame.locator(FMT_BTN[name]).first
        if frame.locator(FMT_BTN[name]).count() == 0:
            return False
        cls = btn.get_attribute("class", timeout=800) or ""
        pressed = btn.get_attribute("aria-pressed", timeout=300) or ""
        return "is-selected" in cls or "is-active" in cls or pressed == "true"
    except Exception:
        return False


def set_fmt(frame, name, want):
    if fmt_on(frame, name) != want:
        try_click(frame, [FMT_BTN[name]], timeout=1500)
        time.sleep(0.2)


def set_bold(frame, want):
    set_fmt(frame, "bold", want)


def clear_formats(frame, keep_bold=False):
    """취소선/밑줄/기울임이 켜져 있으면 끄기 (글 쓰기 전에 매번 확인)"""
    for name in ("strike", "underline", "italic"):
        set_fmt(frame, name, False)
    if not keep_bold:
        set_fmt(frame, "bold", False)


def try_click(frame, selectors, timeout=1500):
    for sel in selectors:
        try:
            loc = frame.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            loc.click()
            return True
        except Exception:
            continue
    return False


def get_editor_frame(page):
    """스마트에디터는 보통 mainFrame iframe 안에 있어요. 없으면 페이지 자체."""
    try:
        page.wait_for_selector("iframe#mainFrame", timeout=15000)
        for _ in range(30):
            fr = page.frame(name="mainFrame")
            if fr and fr.url and "about:blank" not in fr.url:
                return fr
            time.sleep(0.5)
    except Exception:
        pass
    return page.main_frame


def dismiss_popups(frame):
    # "작성 중인 글이 있습니다" -> 취소(새 글), 도움말 패널 닫기
    try_click(frame, [".se-popup-button-cancel", "button:has-text('취소')"], timeout=2500)
    try_click(frame, [".se-help-panel-close-button", "button[class*='help'][class*='close']"], timeout=1500)


def focus_end(page, frame):
    """본문 맨 끝으로 커서 이동"""
    comps = frame.locator(".se-main-container .se-component, .se-components-wrap .se-component")
    last = comps.last
    cls = last.get_attribute("class") or ""
    if "se-text" in cls:
        last.locator(".se-text-paragraph").last.click()
        page.keyboard.press("End")
    else:
        # 마지막이 사진이면 사진을 선택한 뒤 Enter -> 아래에 새 문단
        last.click()
        human_pause(0.3, 0.6)
        page.keyboard.press("Enter")
    human_pause(0.3, 0.6)


def insert_image(page, frame, img):
    imgs = frame.locator(".se-component.se-image")
    before = imgs.count()
    with page.expect_file_chooser(timeout=15000) as fc:
        if not try_click(frame, ["button.se-image-toolbar-button",
                                 "button[data-name='image']",
                                 "button[data-log='dot.img']"], timeout=5000):
            raise RuntimeError("사진 버튼을 못 찾았어요")
    fc.value.set_files(str(img))
    end = time.time() + 60
    while time.time() < end:
        if imgs.count() > before:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError(f"사진 업로드가 끝나지 않았어요: {img.name}")
    time.sleep(1.5)
    focus_end(page, frame)


def save_draft(page, frame):
    if not try_click(frame, ["button[class*='save_btn']", "button:has-text('저장'):not(:has-text('임시'))"], 5000):
        raise RuntimeError("저장 버튼을 못 찾았어요")
    time.sleep(3)


def publish(page, frame, title):
    if not try_click(frame, ["button[class*='publish_btn']", "button:has-text('발행')"], 5000):
        raise RuntimeError("발행 버튼을 못 찾았어요")
    human_pause(1.5, 2.5)
    if ADD_TAGS:
        try:
            box = frame.locator("#tag-input, input[class*='tag_input'], input[placeholder*='태그']").first
            box.wait_for(state="visible", timeout=4000)
            box.click()
            for t in make_tags(title):
                type_text(page, t)
                page.keyboard.press("Enter")
                human_pause(0.2, 0.5)
        except Exception:
            log("  (태그 입력칸을 못 찾아서 태그는 건너뛰어요)")
    human_pause(1, 2)
    # 설정 창 아래쪽 '✓ 발행' 버튼 (위쪽 초록 발행 버튼과 다른 버튼)
    clicked = try_click(frame, ["button[class*='confirm_btn']",
                                "div[class*='layer'] button[class*='confirm']",
                                "div[class*='layer_btn'] button:has-text('발행')"], 5000)
    if not clicked:
        try:
            frame.locator("button:has-text('발행')").last.click(timeout=5000)
            clicked = True
        except Exception:
            pass
    if not clicked:
        raise RuntimeError("설정 창의 발행 버튼을 못 찾았어요")
    # 발행이 끝나면 에디터가 사라지고 글 보기 화면으로 바뀌어요
    end = time.time() + 40
    while time.time() < end:
        time.sleep(1)
        try:
            if "PostView" in page.url or "PostView" in frame.url:
                break
            if frame.is_detached() or frame.locator(".se-documentTitle").count() == 0:
                break
        except Exception:
            break
    else:
        raise RuntimeError("발행 버튼을 눌렀는데 발행이 끝나지 않았어요")
    time.sleep(3)


def write_one(page, post_path, images):
    title = post_path.stem
    blocks = parse_post(post_path)
    slots = image_slots(len(blocks), len(images))
    log(f"작성 시작: {title}  (문단 {len(blocks)}개, 사진 {len(images)}장)")

    page.goto(f"https://blog.naver.com/{BLOG_ID}?Redirect=Write&", wait_until="domcontentloaded")
    time.sleep(3)
    if "nid.naver.com" in page.url:
        raise RuntimeError("로그인이 풀려 있어요. 2_로그인.bat 을 다시 실행하세요.")
    frame = get_editor_frame(page)
    frame.wait_for_selector(".se-documentTitle, .se-section-documentTitle", timeout=40000)
    time.sleep(2)
    dismiss_popups(frame)

    # 제목
    frame.locator(".se-documentTitle .se-text-paragraph, .se-section-documentTitle .se-text-paragraph").first.click()
    human_pause()
    type_text(page, title)
    human_pause()

    # 본문
    frame.locator(".se-component.se-text .se-text-paragraph").first.click()
    human_pause()
    fixed = fixed_image()
    if fixed and FIXED_IMAGE_POSITION == "맨앞":
        log(f"  고정 사진(맨앞): {fixed.name}")
        insert_image(page, frame, fixed)
    for img in named_images(TOP_IMAGES):
        log(f"  고정 사진(위): {img.name}")
        insert_image(page, frame, img)
    img_i = 0
    for bi, (kind, text) in enumerate(blocks):
        lines = text.split("\n")
        clear_formats(frame)
        if kind == "sub" and BOLD_SUBHEADINGS:
            # 소제목: 입력 -> 그 줄 선택 -> 굵게 버튼 -> 줄 끝으로
            type_text(page, text)
            page.keyboard.press("Shift+Home")
            set_bold(frame, True)
            page.keyboard.press("End")
        else:
            for li, line in enumerate(lines):
                type_text(page, line)
                if li < len(lines) - 1:
                    page.keyboard.press("Enter")
        page.keyboard.press("Enter")
        if kind == "sub" and BOLD_SUBHEADINGS:
            set_bold(frame, False)  # 다음 줄은 굵게 해제
        page.keyboard.press("Enter")  # 문단 사이 빈 줄
        human_pause(0.2, 0.5) if FAST_INPUT else human_pause(0.3, 1.0)
        while img_i < len(images) and slots[img_i] == bi:
            log(f"  사진 {img_i + 1}/{len(images)}: {images[img_i].name}")
            insert_image(page, frame, images[img_i])
            img_i += 1
    while img_i < len(images):  # 혹시 남은 사진
        insert_image(page, frame, images[img_i])
        img_i += 1
    if fixed and FIXED_IMAGE_POSITION != "맨앞":
        log(f"  고정 사진(맨끝): {fixed.name}")
        insert_image(page, frame, fixed)
    for img in named_images(END_IMAGES):
        log(f"  고정 사진(맨끝): {img.name}")
        insert_image(page, frame, img)

    human_pause(2, 4)
    try:
        CHECK_DIR.mkdir(exist_ok=True)
        page.screenshot(path=str(CHECK_DIR / f"{title[:40]}.png"))
    except Exception:
        pass
    if MODE == "발행":
        publish(page, frame, title)
    else:
        save_draft(page, frame)
    log(f"완료({MODE}): {title}")


def move_used_images(images, title):
    dest = Path(IMAGES_DIR) / "사용완료" / title
    dest.mkdir(parents=True, exist_ok=True)
    for img in images:
        shutil.move(str(img), str(dest / img.name))


# ---------------------------------------------------------------- 실행 모드
def cmd_login():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        ctx = open_browser(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://nid.naver.com/nidlogin.login")
        print("\n열린 크롬 창에서 직접 네이버 로그인하세요 ('로그인 상태 유지' 체크).")
        input("로그인이 끝나면 이 창으로 돌아와서 Enter 를 누르세요...")
        ctx.close()
    print("로그인 정보가 저장됐어요. 이제 3_미리보기.bat, 4_실행.bat 을 쓰면 돼요.")


def plan():
    posts = pending_posts()
    imgs = list_images()
    big = 10 ** 9
    left_today = max(0, MAX_PER_DAY - today_count()) if MAX_PER_DAY else big
    n = min(len(posts), MAX_PER_RUN or big, left_today)
    jobs = []
    for i in range(n):
        pool, _ = images_for(posts[i].stem, imgs)
        jobs.append((posts[i], random.sample(pool, min(IMAGES_PER_POST, len(pool)))))
    return posts, imgs, left_today, jobs


def cmd_test():
    posts, imgs, left_today, jobs = plan()
    lt = "제한 없음" if not MAX_PER_DAY else f"{left_today}개"
    print(f"남은 글 {len(posts)}개 / 사진 {len(imgs)}장 / 오늘 남은 한도 {lt} / 이번에 작성 {len(jobs)}개 / 모드 {MODE}")

    for post, ims in jobs:
        blocks = parse_post(post)
        subs = [t for k, t in blocks if k == "sub"]
        print(f"\n▶ {post.stem}")
        print(f"   문단 {len(blocks)}개, 소제목 {len(subs)}개: {subs}")
        pool, where = images_for(post.stem, imgs)
        print(f"   사진 폴더: {where} ({len(pool)}장 중 {len(ims)}장)")
        print(f"   사진: {[i.name for i in ims]}  + 고정 {FIXED_IMAGE or '없음'}({FIXED_IMAGE_POSITION})"
              f"  위 {TOP_IMAGES or '-'}  맨끝 {END_IMAGES or '-'}")
        print(f"   사진 위치(문단 번호 뒤): {[s + 1 for s in image_slots(len(blocks), len(ims))]}")
    if not jobs:
        print("\n지금 올릴 글이 없어요 (글/사진 부족, 또는 오늘 한도 도달).")


def cmd_run():
    from playwright.sync_api import sync_playwright
    if BLOG_ID.startswith("여기에"):
        sys.exit("naver_autopost.py 맨 위 BLOG_ID 를 내 블로그 아이디로 바꿔주세요.")
    posts, imgs, left_today, jobs = plan()
    if not jobs:
        cmd_test()
        return
    log(f"이번에 {len(jobs)}개 작성 ({MODE})")
    ERR_DIR.mkdir(exist_ok=True)
    with sync_playwright() as p:
        ctx = open_browser(p)
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.on("dialog", lambda d: d.accept())  # "페이지를 떠나시겠습니까" 등
        for i, (post, ims) in enumerate(jobs):
            try:
                write_one(page, post, ims)
                write_done(post.stem, MODE)
            except Exception as e:
                shot = ERR_DIR / f"{datetime.datetime.now():%m%d_%H%M%S}.png"
                try:
                    page.screenshot(path=str(shot), full_page=True)
                except Exception:
                    pass
                log(f"오류: {post.stem} -> {e}")
                log(f"화면 저장: {shot}  (여기서 멈춰요. 블로그에서 상태 확인 후 다시 실행하세요)")
                break
            if i < len(jobs) - 1 and max(WAIT_MINUTES) > 0:
                wait = random.uniform(*WAIT_MINUTES)
                log(f"다음 글까지 {wait:.0f}분 대기... (창을 닫지 마세요)")
                time.sleep(wait * 60)
        time.sleep(3)
        ctx.close()
    log("끝")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    {"login": cmd_login, "test": cmd_test, "run": cmd_run}.get(mode, cmd_run)()
