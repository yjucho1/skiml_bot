# SKIML Bot

연구실 Slack에서 논문 조사, 대화 요약, 미팅 조율, Notion Q&A, 서버 모니터링을 처리하는
Socket Mode 봇입니다. 모든 사용자 요청은 `@SKIML Bot` 멘션이 있어야 실행됩니다.

## 기능

| 기능 | 요청 예시 | 동작 |
|---|---|---|
| 논문 조사 | `@SKIML Bot Attention Is All You Need 요약` | 공개 원문을 찾아 읽고 근거 수준과 함께 요약 |
| URL 논문 조사 | `@SKIML Bot https://arxiv.org/...` | URL 원문, 공개 저자 원고 또는 초록을 읽고 요약 |
| 채널 요약 | `@SKIML Bot 채널 요약` | 최근 메시지 최대 200개의 결정·액션·미해결 이슈 정리 |
| 쓰레드 요약 | 쓰레드에서 `@SKIML Bot 쓰레드 요약` | 해당 쓰레드의 논의 흐름과 후속 조치 정리 |
| 미팅 조율 | `@SKIML Bot 회의 잡아줘` | 채널 멤버의 free/busy를 조회하고 후보 버튼 제시 |
| Notion Q&A | `@SKIML Bot GPU 서버 예약 규칙이 뭐야?` | 허용된 Notion 페이지를 검색해 출처 링크와 답변 제공 |
| 서버 상태 | `@SKIML Bot 연구실서버 상태 알려줘` | 요청 즉시 master SSH 접속과 Slurm DRAIN 계열 노드 확인 |
| 서버 상태 게시 | 설정된 시작 시각부터 30분마다 | 지정 채널에 같은 Slurm 상태를 자동 게시 |

논문 요약 별칭은 `요약`, `요약해`, `요약해줘`, `써머리`, `summary`, `summarize`를
대소문자와 관계없이 지원합니다. 미팅 요청은 `미팅`, `회의`, `meeting`, `call`과
`어레인지`, `잡아줘`, `예약해줘`, `schedule`, `arrange`, `book`, `set up` 조합을 지원합니다.
서버 상태는 `연구실 서버`, `서버`, `Slurm`, `노드`와 `상태 확인/알려줘` 조합을 지원합니다.
멘션 없는 URL이나 명령은 무시합니다. 별도로 주기 게시 환경변수를 설정한 경우에만 지정 채널에
자동 게시합니다.

## 구조

```text
Slack app_mention / actions
        │
        ├── ResearchAssistant ── PaperResearchAgent
        │                          ├── 원문·초록 읽기
        │                          └── arXiv → OpenAlex 공개본 검색
        ├── DiscussionAssistant ─ Slack history + OpenAI
        ├── MeetingCoordinator ── Google Calendar OAuth
        ├── LabKnowledge ───────── Notion + OpenAI
        └── ServerStatus ────────── SSH → Slurm sinfo
```

외부 SDK 코드는 `src/skiml_bot/adapters`에, 외부 서비스와 독립적인 핵심 로직은
`src/skiml_bot`에 있습니다.

## 빠른 시작

Python 3.10 이상이 필요하며 3.11 이상을 권장합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
```

`.env`의 실제 값을 입력한 뒤 실행합니다.

```bash
set -a
source .env
set +a
skiml-bot
```

Socket Mode를 사용하므로 공개 HTTP 엔드포인트는 필요하지 않습니다.

### 환경변수

| 변수 | 필수 조건 | 설명 |
|---|---|---|
| `SLACK_BOT_TOKEN` | 항상 | `xoxb-` Bot User OAuth Token |
| `SLACK_APP_TOKEN` | 항상 | `connections:write`가 있는 `xapp-` App-Level Token |
| `OPENAI_API_KEY` | 항상 | 논문·대화 요약과 Notion 답변 생성 |
| `OPENAI_MODEL` | 선택 | 기본값 `gpt-5.4-mini` |
| `SKIML_FEATURES` | 선택 | `knowledge,meetings,server_status` 중 활성화할 연동 |
| `NOTION_TOKEN` | `knowledge` | Notion Integration 토큰 |
| `NOTION_ROOT_PAGE_IDS` | `knowledge` | 검색 허용 루트 페이지 ID, 쉼표 구분 |
| `GOOGLE_OAUTH_TOKEN_FILE` | `meetings` | 공용 Google 계정 OAuth 토큰 파일 |
| `SLURM_SSH_TARGET` | `server_status` | `사용자@호스트` 또는 로컬 SSH config의 alias |
| `SLURM_SSH_IDENTITY_FILE` | 선택 | master 접속용 SSH private key 경로 |
| `SLURM_SSH_KNOWN_HOSTS_FILE` | 선택 | 검증된 master host key가 든 파일 경로 |
| `SLURM_SSH_TIMEOUT_SECONDS` | 선택 | SSH 연결 제한 시간, 기본값 10초 |
| `SLURM_STATUS_CHANNEL_ID` | 선택 | 30분 주기 상태를 게시할 Slack 채널 ID |
| `SLURM_STATUS_INTERVAL_SECONDS` | 주기 게시 | 게시 간격, 기본값 1,800초 |
| `SLURM_STATUS_START_AT` | 주기 게시 | 최초 게시 기준 시각, 타임존을 포함한 ISO 8601 |
| `LAB_TIMEZONE` | 선택 | 기본값 `Asia/Seoul` |

논문 조사와 채널·쓰레드 요약은 핵심 기능이라 별도 feature flag 없이 항상 활성화됩니다.

## Slack 앱 설정

1. Slack 앱 관리 화면에서 **From an app manifest**를 선택합니다.
2. 저장소의 `slack-manifest.yaml`을 적용합니다.
3. `connections:write` 권한의 App-Level Token을 만듭니다.
4. 앱을 워크스페이스에 설치하고 `xoxb-`, `xapp-` 토큰을 `.env`에 넣습니다.
5. 사용할 공개·비공개 채널에 봇을 초대합니다.

Manifest는 `app_mention` 이벤트만 구독합니다. 채널·쓰레드 기록 조회에는
`channels:history`, `groups:history`를, 미팅 참석자 이메일 조회에는 `users:read.email`을
사용합니다. manifest를 변경했다면 Slack 앱 설정에 다시 적용하세요.

## 논문 조사 및 대화 요약

논문 조사 에이전트는 요청 URL을 먼저 읽습니다. 제목만 제공되거나 원문 접근이 제한되면
arXiv에서 정확히 일치하는 제목을 우선 찾고, 없으면 OpenAlex에서 합법적인 공개본을 찾습니다.
구독 논문의 원문을 읽을 수 없으면 초록 기반임을 명시하며 확인되지 않은 수치나 세부 방법을
추측하지 않습니다.

| 결과 | 핵심 내용 |
|---|---|
| `[논문 요약 · 조사 에이전트]` | 조사 경로, 근거 수준, 방법, 실험, 정량 결과, 한계 |
| `[채널 요약]` | 주제별 흐름, 결정, 액션 아이템, 미해결 이슈 |
| `[쓰레드 요약]` | 질문부터 결론까지의 흐름과 후속 조치 |

대화에 없는 담당자와 기한은 추측하지 않고 `미정`으로 표시합니다.

## Google Calendar 설정

Workspace 관리자 권한 없이 공용 Google 계정 하나를 OAuth로 연결합니다. 공용 계정이 미팅을
주최하고, Slack 요청자와 채널 멤버 전원이 참석자로 초대됩니다.

1. Google Cloud 프로젝트에서 Calendar API를 활성화합니다.
2. Google Auth Platform에서 External OAuth 앱을 만들고 공용 계정을 테스트 사용자로 추가합니다.
3. 다음 범위를 등록합니다.

```text
https://www.googleapis.com/auth/calendar.freebusy
https://www.googleapis.com/auth/calendar.events.owned
```

4. `데스크톱 앱` OAuth 클라이언트 JSON을 `.secrets/client_secret.json`에 저장합니다.
5. 로컬 브라우저에서 공용 계정으로 인증합니다.

```bash
.venv/bin/skiml-calendar-auth \
  --client-file .secrets/client_secret.json \
  --token-file .secrets/google-calendar-token.json
```

6. 각 연구원은 공용 계정에 자신의 캘린더를 `약속 있음/없음만 보기`로 공유합니다.
7. Slack 프로필 이메일과 공유한 Google Calendar 주소가 같은지 확인합니다.
8. `.env`에 토큰 경로를 설정합니다.

```env
GOOGLE_OAUTH_TOKEN_FILE=.secrets/google-calendar-token.json
```

External 앱을 Testing 상태로 두면 Calendar refresh token이 짧게 만료될 수 있습니다. 운영 전
Google Auth Platform의 게시 상태를 **In production**으로 전환하고 OAuth 인증을 다시 수행하세요.
후보 버튼을 누르기 전에는 일정이 생성되지 않으며, 같은 버튼 이벤트가 재전송돼도 초대는 한
번만 생성됩니다.

## Notion 설정

1. Notion Integration을 만들고 읽기 권한을 부여합니다.
2. 검색을 허용할 최상위 연구실 페이지를 Integration과 공유합니다.
3. 루트 페이지 ID를 쉼표로 구분해 설정합니다.

```env
SKIML_FEATURES=knowledge
NOTION_TOKEN=ntn_...
NOTION_ROOT_PAGE_IDS=page-id-1,page-id-2
```

루트 아래 하위 페이지와 중첩 블록을 읽어 10분간 메모리에 캐시합니다. 검색된 문서만 답변
근거로 사용하며 출처를 찾지 못하면 추측하지 않습니다.

## 연구실 서버 상태 설정

```env
SKIML_FEATURES=server_status
SLURM_SSH_TARGET=bot-user@login.example.edu
SLURM_SSH_IDENTITY_FILE=.secrets/slurm-monitor
SLURM_SSH_KNOWN_HOSTS_FILE=.secrets/known_hosts
SLURM_STATUS_CHANNEL_ID=C0123456789
SLURM_STATUS_INTERVAL_SECONDS=1800
SLURM_STATUS_START_AT=2026-09-01T15:00:00+09:00
```

봇이 실행되는 머신에서 먼저 비대화형 접속과 Slurm 출력을 확인합니다.

```bash
ssh -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -i .secrets/slurm-monitor bot-user@login.example.edu \
  "sinfo -N -h -o '%N|%T|%E'"
```

봇은 사용자가 `@SKIML Bot 연구실서버 상태 알려줘`처럼 멘션하면 즉시 같은 명령을 실행합니다.
또한 `SLURM_STATUS_CHANNEL_ID`와 `SLURM_STATUS_START_AT`을 설정하면 기준 시각부터 지정 간격마다
같은 결과를 채널에 게시합니다. 재시작 중 놓친 결과는 몰아서 게시하지 않고 다음 시간 경계부터
재개합니다. SSH 접속 성공 여부, 전체 노드 수와 `DRAIN`, `DRAINED`, `DRAINING` 계열 노드 및
사유를 표시하며 CPU/GPU 사용률은 수집하지 않습니다. SSH 키 교환 중 연결 리셋이나 타임아웃은
2초 간격으로 최대 3회 시도한 뒤에만 실패로 게시합니다.

비밀번호가 필요한 SSH는 지원하지 않습니다. 봇 전용 key를 만들고 master의
`authorized_keys`에 등록한 뒤 private key는 봇 서버에만 둡니다. 호스트 키 검증은 끄지 않으며,
봇 서버에서 한 번 검증한 `known_hosts` 파일을 지정하는 방식을 권장합니다.

## 검증

```bash
.venv/bin/pytest
.venv/bin/mypy src
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```

## Google Compute Engine 배포

Socket Mode는 인바운드 웹 포트가 필요하지 않습니다. 무료 등급 범위에서는 미국 리전의
비선점형 `e2-micro`와 30GB 이하 표준 영구 디스크를 사용합니다. 현재 배포는
`us-west1-b`, `e2-micro`, 표준 디스크 20GB 구성입니다.

`deploy/setup-gce.sh`는 Debian VM에 `skimlbot` 시스템 사용자, 가상환경과 systemd 서비스를
설치합니다. 실행 전 `deploy/skiml-bot.service`를 VM의 `/tmp`에 함께 전송해야 합니다. 비밀
파일은 저장소나 VM 이미지에 포함하지 않고 별도로 전송한 뒤 `deploy/install-gce-secrets.sh`로
권한을 `0600`으로 제한합니다. `deploy/ssh-config.example`을 복사해 실제 호스트·사용자·포트를
입력한 `deploy/ssh-config`는 Git에 커밋하지 않습니다.

서비스 관리 명령은 다음과 같습니다.

```bash
sudo systemctl status skiml-bot
sudo systemctl restart skiml-bot
sudo journalctl -u skiml-bot -f
```

배포 업데이트 시 저장소를 pull하고 설치 스크립트를 다시 실행한 뒤 서비스를 재시작합니다.
로컬과 클라우드에서 봇을 동시에 실행하면 Slack 이벤트와 주기 게시가 중복되므로 운영
인스턴스는 한 대만 실행해야 합니다.

## Docker 배포

OAuth 토큰은 Git이나 이미지에 포함하지 말고 서버로 별도 전송합니다. 현재 구현은 access token
갱신 후 JSON을 다시 저장하므로 컨테이너 사용자가 토큰 파일을 읽고 쓸 수 있어야 합니다.

```bash
docker build -t skiml-bot .

docker run --env-file .env \
  -e GOOGLE_OAUTH_TOKEN_FILE=/run/secrets/google-calendar-token.json \
  -e SLURM_SSH_IDENTITY_FILE=/run/secrets/slurm-monitor \
  -e SLURM_SSH_KNOWN_HOSTS_FILE=/run/secrets/known_hosts \
  -v /srv/skiml-bot/secrets/google-calendar-token.json:/run/secrets/google-calendar-token.json:rw \
  -v /srv/skiml-bot/secrets/slurm-monitor:/run/secrets/slurm-monitor:ro \
  -v /srv/skiml-bot/secrets/known_hosts:/run/secrets/known_hosts:ro \
  skiml-bot
```

이미지는 UID/GID `65532`로 실행됩니다. Calendar 토큰은 읽고 쓸 수 있어야 하며 SSH 파일은
읽기만 가능하면 됩니다.

```bash
sudo chown 65532:65532 /srv/skiml-bot/secrets/google-calendar-token.json
sudo chmod 600 /srv/skiml-bot/secrets/google-calendar-token.json
sudo chown 65532:65532 /srv/skiml-bot/secrets/slurm-monitor /srv/skiml-bot/secrets/known_hosts
sudo chmod 400 /srv/skiml-bot/secrets/slurm-monitor /srv/skiml-bot/secrets/known_hosts
```

Socket Mode와 미팅 후보의 멱등성 상태는 프로세스 메모리에 있으므로 현재 버전은 단일 인스턴스로
실행해야 합니다. 다중 인스턴스에서는 이벤트 처리 및 미팅 후보 저장소를 Redis나 데이터베이스로
교체해야 합니다.

## 보안

- `.env`, `.secrets/`, OAuth client JSON과 token JSON을 커밋하지 않습니다.
- Google·Slack·OpenAI·Notion 토큰은 Secret Manager 또는 접근 제한된 파일로 보관합니다.
- 토큰이 노출되면 해당 서비스에서 즉시 취소하고 재발급합니다.
- Google 공용 계정의 비밀번호를 공유하지 말고 OAuth 토큰만 봇 런타임에 제공합니다.
- master SSH private key는 봇 런타임만 읽게 하고 Git이나 Docker 이미지에 포함하지 않습니다.
