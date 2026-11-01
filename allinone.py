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

# 주제별 제목 문구 (제목 = "[지역] [동] " + 문구). 글마다 아래에서 골라 써서 제목이 매번 달라져요.
# 사진 폴더를 고르는 단어(변기/세면대/싱크대/수전)는 꼭 넣고, 다른 주제 단어는 섞지 마세요.
TOPICS = {
    "변기": [
        "변기막힘 뚫음 업체 추천 및 뚫는 비용 안내",
        "변기 뚫는 비용 및 고장 수리 업체 추천",
        "변기막힘 고장 출장 수리 업체 비용 총정리",
        "변기 막힘 뚫는업체 추천 및 원인별 해결 방법",
        "변기뚫음 전문업체 비용 및 막힘 재발 방지",
        "변기 물 안내려갈때 뚫음 업체 비용 및 해결",
        "변기 고장 및 막힘 뚫음 업체 비용 알아보기",
        "변기뚫는비용 및 막힘해결 업체 추천",
    ],
    "세면대": [
        "세면대막힘 업체 추천 및 뚫는 비용 안내",
        "세면대 물 안내려갈때 막힘 뚫음 업체 비용",
        "세면대 배수구 막힘 고장 수리 업체 추천",
        "세면대막힘 뚫는비용 및 배수 고장 해결 업체",
        "세면대 배수관 막힘 원인과 뚫음 업체 비용",
        "세면대 팝업 배수구 고장 및 막힘 수리 업체",
        "세면대막힘 비용 및 막힘해결 업체 추천",
    ],
    "싱크대": [
        "싱크대막힘 뚫음 업체 추천 및 비용 안내",
        "싱크대 배수구 막힘 고장 수리 업체 비용",
        "주방 싱크대 물 안내려갈때 뚫는 업체 추천",
        "싱크대막힘 뚫는비용 및 기름때 막힘 해결 업체",
        "싱크대 하수구 역류 막힘 뚫음 전문업체",
        "싱크대 배관 막힘 원인과 뚫는 비용 업체 추천",
        "싱크대막힘 비용 및 막힘해결 업체 추천",
    ],
    "수전": [
        "수전교체 업체 추천 및 교체 비용 안내",
        "수전 고장 누수 수리 및 교체 업체 비용",
        "수도꼭지 수전 고장 교체 업체 추천 및 비용",
        "수전 물샘 누수 교체 수리 업체 비용 총정리",
        "주방 수전교체 비용 및 누수해결 업체 추천",
        "수전교체비용 및 수도꼭지 고장 해결 업체",
        "수전교체비용 및 누수해결 업체 추천",
    ],
}

# 7번 글 길이 (5/6번보다 약 20% 길게)
LENGTH_OLD = "전체 문단 수 12~15개, 글자 수 공백 포함 650~900자. 길게 쓰지 마."
LENGTH_NEW = "전체 문단 수 14~18개, 글자 수 공백 포함 800~1100자."

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
    if LENGTH_OLD in gp.SYSTEM:
        gp.SYSTEM = gp.SYSTEM.replace(LENGTH_OLD, LENGTH_NEW)
    else:
        print("※ 글 길이 설정을 못 바꿨어요 (gen_posts.py 문구가 달라요). 기존 길이로 써요.")
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
    pools = {k: random.sample(v, len(v)) for k, v in TOPICS.items()}
    for d in dongs:
        if sets >= count:
            break
        prefix = f"{region} {d} "
        items = []
        for word, pool in pools.items():
            # 이 동에서 이 주제로 이미 발행한 글이 있으면 건너뛰어요 (제목 문구가 달라도)
            if any(t.startswith(prefix) and word in t for t in done):
                continue
            phrase = pool[len(plan + items) % len(pool)]
            items.append((d, prefix + phrase))
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
    made = gp.generate_many(client, region, plan, out_dir)

    if not made:
        sys.exit("\n만든 글이 없어서 발행은 건너뛰어요.")

    # 바로 발행 (4번과 같은 설정, 글 폴더만 이번 폴더로)
    print(f"\n=== 글 {made}개 생성 완료. 블로그 발행을 시작해요 (모드: {ap.MODE}) ===")
    print("크롬 창이 끝날 때까지 마우스/키보드를 건드리지 마세요.\n")
    ap.POSTS_DIR = str(out_dir)
    ap.EXTRA_TAGS = [biz]
    ap.TOP_IMAGES = ["2.png"]   # 1.png 다음에 2.png
    ap.END_IMAGES = ["2.png"]   # 글 맨 마지막에 2.png 한 번 더
    ap.cmd_run()


if __name__ == "__main__":
    main()
