# 스팀 게임 달력

Steam 게임의 **출시일 · 할인율 · 할인 종료일 · 가격**을 달력으로 보여주는 사이트예요.
- 매일 **오전 3시, 오후 3시(한국시간)**에 자동으로 갱신돼요.
- 날짜가 확정 안 된 게임(분기·연도·미정)은 오른쪽 **날짜 미확정** 목록에 따로 모이고,
  갱신할 때마다 다시 확인해서 날짜가 정해지면 **최근 날짜 확정**에 표시돼요.
- 출시일이 바뀐 게임(연기 등)은 **일정 변경** 표시가 붙어요.
- 비용: 0원 (GitHub 무료 기능만 사용)

---

## 처음 한 번만 하는 설치 (약 10분)

### 1. GitHub 가입
https://github.com 에서 가입하고 로그인하세요.

### 2. 저장소(프로젝트 폴더) 만들기
1. 오른쪽 위 **+** → **New repository**
2. Repository name: `steam-calendar`
3. **Public** 선택 (무료로 사이트를 열려면 Public 이어야 해요)
4. **Create repository** 클릭

### 3. 파일 올리기
1. 받은 압축 파일을 풀어요.
2. 저장소 화면에서 **uploading an existing file** 링크를 누르세요.
3. 압축 푼 폴더 안의 `site`, `scripts`, `tests` 폴더와 `README.md` 를 끌어다 놓으세요.
4. 아래 **Commit changes** 클릭

> `.github` 폴더는 맥·윈도에서 숨김 폴더라 잘 안 올라가요. 그래서 5번에서 따로 만들어요.

### 4. 사이트 공개 설정
1. 저장소 위쪽 **Settings** → 왼쪽 **Pages**
2. **Source** 를 **GitHub Actions** 로 바꾸기
3. 같은 Settings 에서 왼쪽 **Actions → General** → 맨 아래 **Workflow permissions** 를
   **Read and write permissions** 로 바꾸고 **Save**

### 5. 자동 갱신 파일 만들기
1. 저장소 첫 화면 → **Add file** → **Create new file**
2. 파일 이름 칸에 그대로 입력: `.github/workflows/update.yml`
3. 압축 파일 안 `.github/workflows/update.yml` 내용을 전부 복사해서 붙여넣기
   (메모장으로 열면 돼요. 안 보이면 이 README 맨 아래에도 같은 내용이 있어요.)
4. **Commit changes** 클릭 → 이 순간 첫 갱신이 바로 시작돼요.

### 6. 확인
1. 저장소 위쪽 **Actions** 탭 → **스팀 데이터 갱신** 이 노란색(진행 중)으로 돌아요.
   처음엔 게임이 많아서 **10~30분** 걸려요.
2. 초록색 ✔ 가 되면 사이트 주소로 들어가세요:
   **https://내아이디.github.io/steam-calendar/**
   (Settings → Pages 에도 주소가 나와요)

---

## 직접 갱신하기
- 사이트 오른쪽 위 **⚡ 지금 갱신하기** → GitHub 화면에서 **Run workflow** → 초록 **Run workflow**
- 끝나면(10~30분) 사이트에서 **↻ 새로 불러오기**

## 알아두면 좋은 점
- GitHub 자동 실행은 바쁜 시간에 **10~30분 정도 늦게** 시작될 수 있어요.
- 할인 **시작일**은 Steam이 공개하지 않아 **종료일**만 표시해요. 일부 게임은 종료일도 비공개예요.
- 가격은 **한국 원화(₩)** 기준이에요.
- Steam에는 게임이 10만 개가 넘어서, 매번 **출시 예정 전체 + 최근 출시 3,000개 + 할인 중 최대 10,000개**를 받아오고
  이전 데이터와 합쳐 쌓아요. 숫자는 `scripts/update_steam.py` 맨 위에서 바꿀 수 있어요.
- 오랫동안(60일) 저장소에 변화가 없으면 GitHub가 자동 실행을 멈출 수 있어요.
  메일이 오면 Actions 탭에서 **Enable workflow** 를 눌러주세요.
- GitHub 에 올리기 전(첫 갱신 전)에 화면을 열면 **예시 데이터**가 보여요. 첫 갱신이 끝나면 실제 데이터로 바뀌어요.

## 폴더 구성
```
site/index.html            달력 화면
site/data/games.json       갱신된 게임 데이터 (자동 생성)
scripts/update_steam.py    Steam 에서 데이터 받아오는 프로그램
.github/workflows/update.yml  자동 갱신 시간표 (오전 3시·오후 3시)
tests/test_update.py       동작 확인용 테스트
```

---

## update.yml 내용 (5번에서 붙여넣을 내용)
```yaml
name: 스팀 데이터 갱신

on:
  schedule:
    # GitHub 시계는 세계표준시(UTC)라서 9시간을 빼서 적어요.
    # 18:00 UTC = 한국 오전 3시, 06:00 UTC = 한국 오후 3시
    - cron: "0 18 * * *"
    - cron: "0 6 * * *"
  workflow_dispatch: {}      # 'Run workflow' 버튼으로 직접 갱신
  push:
    branches: [main]
    paths: ["site/index.html", "scripts/**", ".github/workflows/**"]

permissions:
  contents: write
  pages: write
  id-token: write

concurrency:
  group: steam-update
  cancel-in-progress: false

jobs:
  update:
    runs-on: ubuntu-latest
    timeout-minutes: 90
    environment:
      name: github-pages
      url: ${{ steps.deploy.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Steam에서 데이터 받아오기
        run: python scripts/update_steam.py

      - name: 받은 데이터 저장
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898233+github-actions[bot]@users.noreply.github.com"
          git add site/data
          if git diff --cached --quiet; then
            echo "바뀐 내용 없음"
          else
            git commit -m "데이터 갱신 $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M')"
            git pull --rebase origin main || true
            git push
          fi

      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site
      - name: 사이트에 올리기
        id: deploy
        uses: actions/deploy-pages@v4
```
