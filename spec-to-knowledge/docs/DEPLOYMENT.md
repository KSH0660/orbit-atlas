# 배포·운영 가이드 (RHEL 8.10 폐쇄망)

대상 환경은 RHEL 8.10(x86_64), Python 3.11.9, 인터넷 차단입니다. Node.js 18이 설치돼 있어도 쓰지 않습니다(UI는 빌드 없는 정적 파일).

## 1. 준비물

| 위치 | 필요한 것 |
|---|---|
| 외부망 PC (번들 생성) | Python 3.11과 pip, 인터넷. OS는 무관하지만 Linux나 WSL을 권장합니다. 대상 플랫폼 휠을 받으므로 RHEL이 아니어도 됩니다. |
| 폐쇄망 서버 | `python3.11`(RHEL 8 AppStream: `dnf install python3.11`), 디스크 수 GB(문서당 원본·이미지·결과), 사내 모델 API 접근 |

컴파일러, Node.js, 데이터베이스, 메시지 큐는 필요 없습니다.

## 2. 오프라인 번들 만들기 (외부망)

```bash
git clone <repo> && cd spec-to-knowledge
PYTHON=python3.11 scripts/build_offline_bundle.sh ./out              # 기본
PYTHON=python3.11 scripts/build_offline_bundle.sh ./out --with-mkdocs  # 결과 열람용 MkDocs 포함
```

결과물은 다음과 같습니다.

- `out/spec2kb-offline-<버전>.tar.gz`, `.sha256`
- 압축 안 내용: `wheelhouse/`(manylinux2014/2_28 · cp311 휠과 spec2kb 휠), `SHA256SUMS`, `requirements.txt`, `install_offline.sh`, `deploy/`, `docs/`, `samples/`, `README.md`

반입 전에 `sha256sum -c spec2kb-offline-<버전>.tar.gz.sha256`으로 무결성을 확인합니다.

## 3. 설치 (폐쇄망 서버)

```bash
sudo dnf install -y python3.11            # 사내 미러 저장소 사용
tar xzf spec2kb-offline-1.0.0.tar.gz && cd spec2kb-offline-1.0.0
sudo ./install_offline.sh
```

설치 스크립트가 하는 일:

1. 휠 체크섬 검증(`SHA256SUMS`)
2. `/opt/spec2kb/venv` 생성 후 `pip install --no-index --find-links wheelhouse`로 설치(네트워크 미사용)
3. 서비스 계정 `spec2kb`, 데이터 폴더 `/var/lib/spec2kb`, 설정 `/etc/spec2kb/spec2kb.env`(권한 640) 생성
4. `/etc/systemd/system/spec2kb.service` 설치
5. `spec2kb doctor --full` 자가 점검: 내장 샘플 PDF 변환, 검증 오류 0건, ZIP 생성 확인

경로는 `PREFIX`, `DATA_DIR`, `ENV_DIR`, `SERVICE_USER`, `PYTHON` 환경변수로 바꿀 수 있습니다. 시스템 계정이나 유닛 없이 사용자 계정에 설치하려면 `SKIP_SYSTEM=1 PREFIX=$HOME/spec2kb DATA_DIR=$HOME/spec2kb-data ./install_offline.sh`를 실행합니다.

## 4. 설정과 기동

`/etc/spec2kb/spec2kb.env`([템플릿](../deploy/spec2kb.env.example)):

```ini
S2K_HOST=0.0.0.0
S2K_PORT=8765
S2K_DATA_DIR=/var/lib/spec2kb
S2K_WORKERS=2
S2K_BASIC_AUTH=admin:<비밀번호>          # 또는 리버스 프록시 SSO
S2K_DEFAULT_PROVIDER=corp-vlm
S2K_CA_BUNDLE=/etc/pki/tls/certs/corp-root-ca.pem
S2K_PROVIDERS_SEED=/etc/spec2kb/providers.json   # 첫 기동 시 Provider 자동 등록 (선택)
INTERNAL_LLM_KEY=<사내 모델 키>                  # Provider의 api_key_env가 참조
```

```bash
sudo systemctl enable --now spec2kb
sudo systemctl status spec2kb
journalctl -u spec2kb -f                         # 로그
```

방화벽과 SELinux:

```bash
sudo firewall-cmd --add-port=8765/tcp --permanent && sudo firewall-cmd --reload
# nginx 리버스 프록시를 쓸 때 (SELinux enforcing)
sudo setsebool -P httpd_can_network_connect 1
```

리버스 프록시 예시는 [deploy/nginx-spec2kb.conf.example](../deploy/nginx-spec2kb.conf.example)에 있습니다. 업로드 한도(`client_max_body_size`)와 ZIP 내보내기 시간(`proxy_read_timeout`)을 함께 늘려야 합니다.

## 5. 사내 모델 연결

1. 웹 UI에서 ‘모델 / API’ → ‘Provider 추가’를 누릅니다.
   - OpenAI 호환(vLLM·TGI·LiteLLM·사내 게이트웨이): Base URL `https://llm-gw.corp.local/v1`, 모델명, `api_key_env`
   - 형식이 다른 OCR/Vision API: Custom HTTP 요청 템플릿과 응답 경로([PROVIDERS.md](PROVIDERS.md))
2. ‘연결 테스트’를 누릅니다. 작은 이미지와 함께 요청을 보내 응답과 지연 시간을 보여 줍니다.
3. 프로필의 ‘AI 그림 해석 → Vision 모델(Provider)’에 Provider ID를 지정하거나, `S2K_DEFAULT_PROVIDER`로 서버 기본값을 정합니다.

CLI로 점검하려면 `sudo -u spec2kb /opt/spec2kb/venv/bin/spec2kb doctor --data-dir /var/lib/spec2kb --test-provider corp-vlm`을 실행합니다(이때 `EnvironmentFile`의 키 변수를 export해야 합니다).

## 6. 인수 시험 (설치 직후 권장)

1. `samples/jedec_like_spec.pdf`를 JEDEC 프로필로 변환해 오류 0건, 표 3개, 그림 3개가 나오는지 확인합니다.
2. 같은 문서를 사내 Vision Provider로 다시 변환해 그림 설명의 상태(확인됨/검토 필요)와 응답 시간을 확인합니다.
3. 대표 실문서 3~5건(JEDEC 1~2건, 고객 사양서, 데이터시트)을 변환하고 ‘검증 결과’에서 오류 유형을 확인한 뒤 필요하면 상속 프로필로 패턴을 조정합니다.
4. ZIP을 받아 `mkdocs build --strict` 또는 사내 Wiki에 올려 링크와 이미지를 확인합니다.

## 7. 운영

| 항목 | 방법 |
|---|---|
| 데이터 위치 | `S2K_DATA_DIR` 아래에 `docs/<id>/`(원본·결과·이미지·수정 내용), `profiles/`, `providers.json`, `cache/vision/`, `exports/`(최근 ZIP 30개) |
| 백업 | 서비스를 중지하거나 작업이 없을 때 `S2K_DATA_DIR` 전체를 백업합니다(파일 기반이라 rsync/tar로 충분). 설정만 백업하려면 `profiles/`와 `providers.json`(키 포함 가능, 권한 주의)을 챙깁니다. |
| 용량 관리 | 문서를 삭제하면 해당 폴더 전체가 지워집니다. `cache/vision/`은 지워도 됩니다(다음 변환 때 다시 호출). `exports/`는 자동으로 30개만 남깁니다. |
| 업그레이드 | 새 번들로 `install_offline.sh`를 다시 실행합니다(venv 재설치, 데이터 유지). 그다음 `systemctl restart spec2kb`. Canonical 스키마 버전은 `schema_version`에 기록됩니다. |
| 동시성 | 문서 병렬 처리 수는 `S2K_WORKERS`, 그림 설명 동시 호출 수는 프로필의 ‘동시 호출 수’로 정합니다(사내 API 한도에 맞춤). 서버는 **단일 프로세스**로 운영해야 합니다(멀티 워커 금지). |
| 장애 시 | 서버를 재시작하면 처리 중이던 작업이 ‘실패’로 표시되며, 문서를 다시 변환하면 됩니다. 사용자 수정 내용은 유지됩니다. |
| 로그 | stdout/stderr를 journald로 보냅니다. `S2K_LOG_LEVEL=DEBUG`로 상세 로그를 남길 수 있습니다. API Key와 이미지 데이터는 로그에 남기지 않습니다. |
| 보안 | Basic 인증(`S2K_BASIC_AUTH`) 또는 SSO 리버스 프록시를 사용합니다. API Key는 `api_key_env`(환경변수)로 지정하고, `S2K_ALLOW_API_KEY_STORAGE=0`으로 파일 저장을 막을 수 있습니다. 데이터 파일 권한은 0600입니다. |

## 8. 문제 해결

| 증상 | 확인할 것 |
|---|---|
| 설치 중 `No matching distribution` | 번들을 Python 3.11·x86_64용으로 만들었는지, `PYTHON=python3.11`로 설치했는지 확인합니다. |
| `doctor`의 PDF 렌더 실패 | 이 머신에서 `pypdfium2` 휠이 import되는지 확인합니다(`python -c "import pypdfium2"`). glibc 2.17 이상이 필요합니다. |
| 그림 설명이 모두 `vision_failed` | ‘연결 테스트’로 확인합니다. 인증서 오류면 `S2K_CA_BUNDLE`, 프록시면 `HTTPS_PROXY`/`NO_PROXY`, 401이면 키 환경변수가 systemd 환경에 들어갔는지 봅니다. |
| 응답 형식 오류(검토 필요, “JSON 형식이 아님”) | 모델이 JSON을 지키지 않는 경우입니다. 프로필의 시스템 프롬프트를 강화하거나 temperature 0, `extra_body`에 `{"response_format": {"type": "json_object"}}`(지원하는 서버)를 넣습니다. |
| 제목이 본문으로 처리되거나 그 반대 | 프로필 → 파싱 → 제목: 번호 패턴, ‘강조 필수’, ‘번호 순서 검사’를 확인합니다. |
| 머리글이 본문에 남음 | 프로필 → 머리글/바닥글: 상·하단 영역 비율, ‘추가 제거 패턴’을 확인합니다. |
| 표가 그림으로 잡히거나 그 반대 | 캡션 패턴과 캡션 위치(JEDEC은 표 위·그림 아래)를 확인합니다. |
| 업로드 413 | `S2K_MAX_UPLOAD_MB`와 리버스 프록시의 `client_max_body_size`를 확인합니다. |
