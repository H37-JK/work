# -*- coding: utf-8 -*-
"""
한 번에: 지역 + 업체명 + 개수 입력 -> 변기/세면대/싱크대/수전 글 생성 -> 바로 블로그 발행

    py allinone.py
"""
import re
import sys
import random
import datetime
from pathlib import Path

import anthropic

import gen_posts as gp
import naver_autopost as ap

# 주제별 키워드 문구 (제목 = "[지역] [동] " + 문구)
TOPICS = [
    "변기뚫는비용 및 막힘해결 업체 추천",
    "세면대막힘 비용 및 막힘해결 업체 추천",
    "싱크대막힘 비용 및 막힘해결 업체 추천",
    "수전교체비용 및 누수해결 업체 추천",
]

BASE = Path(__file__).resolve().parent


def main():
    print("=== 글 생성 + 블로그 발행 한 번에 ===\n")
    region = gp.ask("지역 (예: 영등포구, 운정, 일산): ")
    if not region:
        sys.exit("지역을 입력해야 해요.")
    biz = gp.ask("업체명 [Enter = 토일케어]: ", "토일케어")
    try:
        count = int(gp.ask("몇 세트 만들까요? (1 = 변기/세면대/싱크대/수전 각 1개씩 총 4개): ", "0"))
    except ValueError:
        count = 0
    if count <= 0:
        sys.exit("개수를 숫자로 입력해야 해요.")
    dong_in = gp.ask("동 이름 직접 입력 (쉼표로 구분, Enter = 자동으로 찾기): ")

    # 업체명 반영
    gp.SYSTEM = gp.SYSTEM.replace(f"'{gp.BUSINESS}'", f"'{biz}'")
    gp.BUSINESS = biz
    if biz not in gp.NAMES.values():
        gp.NAMES[biz] = biz

    key = gp.load_key()
    client = anthropic.Anthropic(api_key=key) if key else anthropic.Anthropic()

    if dong_in:
        dongs = [d.strip() for d in re.split(r"[,，\s]+", dong_in) if d.strip()]
    else:
        print("\n동 목록 찾는 중...")
        dongs = gp.get_dongs(client, region)
        if not dongs:
            sys.exit("동 목록을 못 찾았어요. 동 이름을 직접 입력해 주세요.")
        print(f"찾은 동 {len(dongs)}개: {', '.join(dongs)}")

    # 1세트 = 동 1개 x 4주제(변기/세면대/싱크대/수전). 이미 발행한 제목은 빼요.
    done = ap.done_titles()
    random.shuffle(dongs)
    plan = []
    sets = 0
    for d in dongs:
        if sets >= count:
            break
        items = [(d, f"{region} {d} {t}") for t in TOPICS if f"{region} {d} {t}" not in done]
        if not items:
            continue
        plan += items
        sets += 1
    if sets < count:
        print(f"※ 새로 쓸 수 있는 동이 {sets}개뿐이라 {sets}세트만 만들어요.")
    print(f"이번 동: {', '.join(dict.fromkeys(d for d, _ in plan))}")

    stamp = datetime.datetime.now().strftime("%m%d_%H%M")
    out_dir = BASE / f"{region} 글 {stamp} ({biz})"
    out_dir.mkdir(exist_ok=True)

    print(f"\n업체명: {biz} / {len(plan)}개 생성 → {out_dir.name}")
    sample = gp.SAMPLE_FILE.read_text(encoding="utf-8-sig") if gp.SAMPLE_FILE.exists() else ""
    angles = random.sample(gp.ANGLES, len(gp.ANGLES))
    made = 0
    for i, (dong, phrase) in enumerate(plan):
        angle = angles[i % len(angles)]
        print(f"\n[{i + 1}/{len(plan)}] {phrase}  (관점: {angle})")
        text = ""
        for attempt in range(2):
            try:
                text = gp.clean(gp.write_post(client, region, dong, phrase, angle, sample))
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
            problems = gp.check(text, phrase)
            if not problems:
                break
            print(f"  다시 쓰는 중 ({', '.join(problems)})")
        if not text:
            print("  실패해서 건너뛰어요.")
            continue
        (out_dir / f"{phrase}.txt").write_text(text, encoding="utf-8", newline="")
        made += 1
        print(f"  저장 완료 ({len(text)}자)")

    if not made:
        sys.exit("\n만든 글이 없어서 발행은 건너뛰어요.")

    # 바로 발행 (4번과 같은 설정, 글 폴더만 이번 폴더로)
    print(f"\n=== 글 {made}개 생성 완료. 블로그 발행을 시작해요 (모드: {ap.MODE}) ===")
    print("크롬 창이 끝날 때까지 마우스/키보드를 건드리지 마세요.\n")
    ap.POSTS_DIR = str(out_dir)
    ap.EXTRA_TAGS = [biz]
    ap.cmd_run()


if __name__ == "__main__":
    main()
