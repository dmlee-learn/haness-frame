# 테스트 프로젝트 매뉴얼

## 목적

생성 프로젝트에서 프로젝트 생성, 역할 라우팅, 증거 수집, AI 토론,
의사결정 승인, 구현, 실행 테스트, 독립 검토와 제한된 수정 루프를 검증합니다.

## 프로젝트 생성

```powershell
python .\src\haness_frame.py create-project --project "harness-test" "Build a small test application"
cd .\projects\harness-test
```

## 런타임 검증

```powershell
python app.py check --no-probe
python app.py check
python app.py live-check --role planner
python app.py qualify
python app.py qualify --probe-services --run-verification
python app.py runs --unresolved
python app.py summary
python app.py role-plan --task "실패한 import를 수정하고 회귀 테스트를 추가"
python app.py orchestrate --stage planning --task "요청 변경을 설계"
python app.py orchestrate --stage debate --task "구현 대안을 비교"
python app.py orchestrate --stage repair --task "승인된 구현을 수정"
python app.py orchestrate-status --id latest
python app.py orchestrate-resume --id EXECUTION_ID
python app.py orchestrate-reconcile --id EXECUTION_ID
python app.py orchestrate-reconcile-all --limit 100
python app.py orchestrate-abandon --id EXECUTION_ID --reason "대체된 orchestration"
python app.py search-plan
python app.py search-discover
python app.py evidence-draft
python app.py evidence-gaps
python app.py evidence-check
python app.py evidence-rebuild
python app.py claim-add --claim "선택한 API가 호환성을 유지한다" --support-url "https://example.com/source"
python app.py claim-check
python app.py claims
python app.py evidence-fetch --url "https://example.com/source" --query "source question" --why-it-matters "Design constraint" --recommended-use "Use in the decision record"
python app.py evidence-source-check --url "https://example.com/source"
python app.py evidence-source-check-all
python app.py evidence-source-refresh --url "https://example.com/source"
python app.py gate
python app.py verify
python app.py verification-plan
python app.py verification-run
python app.py patch-plan --file workspace/candidate.diff
python app.py patch-apply --file workspace/candidate.diff
python app.py archive --label "verified"
python app.py archive-verify
python app.py audit-check
python app.py audit-export
python app.py ai-cache-status
python app.py ai-cache-prune --max-age-seconds 86400
python app.py repair-run --task "Fix the failing implementation"
python app.py repair-status
python app.py repair-resume --id SESSION_ID
python app.py repair-abandon --id SESSION_ID --reason "대체된 수정 작업"
python app.py invoke --role planner --prompt "Summarize the project state" --json
python app.py debate-rounds --prompt "Compare the implementation options" --rounds 2
python app.py debate-status --id latest
python app.py debate-resume --id DEBATE_ID
python app.py debate-abandon --id DEBATE_ID --reason "수정된 요구사항으로 대체"
python app.py pipeline-status --id latest
python app.py pipeline-resume --id RUN_ID
python app.py pipeline-abandon --id RUN_ID --reason "Superseded run"
```

`live-check --role ROLE`은 실제 로컬 provider 환경을 명시적으로 검증하는 명령입니다.
설정된 모든 service의 endpoint와 모델 목록을 먼저 확인하고, 선택한 role로 작은 생성
호출을 한 번 수행합니다. JSON 결과에는 service identity, fallback 사용 여부, 시도 횟수,
응답 길이와 SHA-256만 포함되며 고정 probe prompt와 응답 본문은 노출하지 않습니다.
설정, 모델 탐색, 연결 또는 생성 호출이 실패하면 비정상 종료합니다. 환경에 의존하므로
기본 offline 자동 테스트에는 포함하지 않습니다.
생성 요청 timeout의 기본값은 120초입니다. 모델에 다른 제한이 필요하면
`workspace/services.json`의 role 또는 fallback service에 1~600 범위의 정수
`request_timeout_seconds`를 지정할 수 있습니다. 잘못된 값은 네트워크 요청 전에
설정 오류로 차단됩니다.

먼저 `check --no-probe`로 네트워크 요청 없이 provider 유형, URL, 모델명,
활성화 상태와 필수 API 키 환경 변수를 검사합니다. provider가 실행 중일 때
`check`를 사용하면 여러 역할이 공유하는 동일 endpoint를 한 번만 탐색합니다.
HTTP(S) URL 구조와 설정된 fallback도 검사하며 URL 내 자격증명, query, fragment는
거부합니다. 실제 invoke도 같은 검사 후 primary와 fallback을 사용합니다.
같은 canonical route의 provider 별칭과 동등 URL은 한 번만 probe하고 fallback으로
재시도하지 않습니다. 활성 상태나 검증 결과가 다르면 별도 오류로 유지합니다.
손상된 `services.json`과 잘못된 service map 구조는 원문을 노출하지 않는 명시적
configuration 오류가 되며 `qualify`와 직접 role invoke에도 같은 원인이 유지됩니다.
생성된 state·service snapshot은 프로젝트 필수 역할을 선언합니다. 선언된 역할의
`role_services` key가 빠지면 unassigned로 보고 qualification을 차단합니다. 역할
계약이 없는 독립 최소 fixture는 사용하는 역할만 부분 구성할 수 있습니다.
선언된 assignment는 state snapshot, service assignment map, 설정 service `name`이
역할별로 일치해야 합니다. 불일치는 service 값을 출력하지 않고 role 기준으로 보고합니다.
실패 원인은 JSON으로 출력되고 scorecard와 audit log에 반영됩니다.

`qualify`는 compile, manifest, 서비스 설정, evidence와 decision gate를 하나의
보고서로 저장합니다. 테스트를 실행하지 않고 모든 조건을 통과하면 `ready`이며,
`--run-verification`으로 승인된 명령까지 통과해야 `qualified`가 됩니다.
`--probe-services`를 추가하면 실제 endpoint와 표준 OpenAI 호환·Ollama 모델 목록의
설정 모델 존재 여부도 검사합니다. 비표준 응답 형식은 HTTP 연결 결과를 유지합니다. 보고서는
`workspace/qualifications/`에 보존됩니다.
manifest는 프로젝트 metadata와 비어 있지 않고 중복 없는 내부 regular file 목록을
가진 JSON object regular file이어야 합니다. unsafe·누락·directory·symlink 항목은
qualification을 차단하며 `manifest` 명령도 invalid 보고서에서 비정상 종료합니다.
`check`와 `qualify`는 coder와 reviewer의 provider·endpoint·model을 비교합니다.
실행 identity가 같으면 readiness를 막지 않는 독립성 경고를 표시하며, 더 강한
검토 독립성이 필요하면 다른 model 또는 endpoint를 사용합니다.
`repair-policy.json`의 `require_independent_reviewer_service`를 `true`로 설정하면
이를 강제합니다. 엄격 모드에서는 coder와 reviewer 실행 identity가 다를 때까지
qualification과 repair 시작·재개를 차단합니다.
repair는 fallback과 cache 응답을 포함해 coder와 reviewer가 실제 사용한 service
identity를 기록합니다. 엄격 모드에서 실제 identity가 같으면 최종 승인을 차단하고
적용된 patch를 rollback 경로로 처리합니다.
OpenAI 호환 provider 별칭과 동등한 endpoint URL 표기는 정규화하므로 adapter 이름,
기본 port 또는 후행 slash만 바꿔 독립 서비스로 판단되게 할 수 없습니다.
엄격 qualification은 approved repair checkpoint에 저장된 실제 identity를 다시
검사합니다. 동일하거나 누락된 durable identity 증거가 있으면 session 상태가
`approved`여도 프로젝트를 차단합니다.
각 approved attempt는 coder identity, reviewer identity, reviewer verdict를
`review_provenance_sha256`으로 묶습니다. 엄격 qualification은 hash 누락이나 승인
후 identity·verdict 변경을 거부합니다.
`orchestration-policy.json`의 `require_independent_debate_judge_service`를
`true`로 설정하면 독립 decision-maker judge를 강제합니다. 설정 identity와 실제
fallback·cache identity가 모든 참가자와 달라야 합니다. `judge_provenance_sha256`은
이 identity들을 verdict·evidence digest와 결합해 decision handoff와 qualification에서 검증합니다.
`check`는 설정 judge가 참가자와 같은 identity를 쓰면 차단하지 않고 경고합니다.
엄격 qualification은 토론 시작 전 이를 차단하며, 기존 session에는 선택된 참가자
역할만 비교한 뒤 실제 실행 identity와 provenance를 다시 검증합니다.

`runs`는 pipeline, debate, repair의 durable session을 prompt나 AI 출력 본문 없이
통합 요약합니다. `--unresolved`를 추가하면 확인이 필요한 실행만 표시하며, 진행
수치와 제한된 실패 이유, 안전한 resume·abandon·점검 명령을 제공합니다.

미해결 최신 repair는 qualification readiness를 차단합니다. `repair-abandon`은
대체된 작업의 종료 사유를 기록하고 active patch가 있으면 먼저 rollback합니다.
이후 사용자 변경과 충돌해 rollback할 수 없으면 `rollback_blocked`를 유지합니다.
성공한 repair는 abandon할 수 없고 abandon한 repair는 재개할 수 없습니다.
Qualification은 최신 pointer뿐 아니라 모든 durable pipeline, debate, repair
session을 검사합니다. 따라서 이후 성공 실행이 과거 failed·running·손상 작업을
숨길 수 없습니다. 남은 시도를 새 repair session으로 정상 인계한 기존 session은
successor ID와 함께 `superseded`로 마감되어 해결 상태가 됩니다.

`research/search-evidence-draft.md`를 작성하고 `evidence-commit`으로 반영한 뒤
`decision-draft`로 의사결정 초안을 만듭니다. `evidence-fetch`는 검색 결과
구조화 JSON을 authoritative 원본으로 사용하며 Markdown 보기보다 먼저 저장합니다.
기존 Markdown 보기가 원본과 다르면 `evidence-check`가 nonzero로 종료합니다.
중단된 저장 이후에는 `evidence-rebuild`로 JSON에서 안전하게 다시 생성합니다.
CI에서 `gate`, `verify`, `claim-check`, `evidence-check`, `verification-plan`,
`verification-run`, `archive-verify`, `audit-check`, `manifest`, `check`는
보고한 조건이 통과할 때만 `0`, 실패하면 `1`을 반환합니다.
페이지가 아닌 직접 원문 URL에 사용합니다. 제목과 제한된 본문을 추출하며,
`workspace/evidence-policy.json`에서 시간, 응답 크기, 본문 길이, content type,
허용 도메인과 사설망 접근 여부를 제어합니다. 사설망과 loopback 주소는
redirect 이후에도 기본적으로 차단됩니다.
`search-evidence.json`은 object record의 JSON list, `search-plan.json`은 JSON
object여야 합니다. malformed·wrong-root 파일은 gate와 qualification을 차단하고
path·위치만 보고합니다. add·refresh·draft commit은 손상 원본을 덮어쓰지 않습니다.
직접 수집한 evidence에는 정규화된 가시 본문의 SHA-256 fingerprint가 저장됩니다.
`evidence-source-check --url URL`은 원문 내용이나 최종 redirect URL 변경을 탐지하고
변경 시 nonzero로 종료합니다. 보고서에는 본문 없이 hash와 metadata만 저장됩니다.
신규 프로젝트는 `direct_url` record의 fingerprint를 요구하며, 기존 프로젝트는
해당 record를 다시 수집한 뒤 `require_source_fingerprint`를 활성화할 수 있습니다.
원문 변경이 탐지되면 evidence policy와 qualification이 차단됩니다. 변경 내용을
검토한 뒤 `evidence-source-refresh`로 record와 verification을 원자적으로 갱신합니다.
새 evidence digest 때문에 decision을 다시 생성할 때까지 구현 gate도 닫힙니다.
주기적 검증을 의무화하려면 `require_source_revalidation`과
`max_source_verification_age_days`를 설정합니다.
`evidence-source-check-all`은 `max_source_checks_per_run` 범위에서 fingerprint가
있는 모든 HTTP 원문을 검사합니다. 개별 실패 후에도 계속 실행하며 변경·오류 또는
제한으로 건너뛴 원문이 하나라도 있으면 nonzero로 종료합니다.

자동 candidate 발견은 선택 기능이며 기본적으로 비활성화됩니다.
`workspace/search-policy.json`에 self-hosted SearXNG endpoint를 설정하고
`enabled`를 true로 바꾼 뒤 현재 계획에는 `search-discover`, 개별 검색에는
`--query`를 사용합니다. 결과는 미승인 candidate일 뿐이며 직접 원문 URL을
가져와 검증하기 전에는 evidence gate에 반영되지 않습니다.

신규 프로젝트는 주장-근거 matrix를 요구합니다. `claim-add`에는 이미 구조화 evidence에
있는 URL만 사용할 수 있습니다. accepted claim에는 supporting source가 필요하고,
challenging source가 있으면 충분한 `--resolution`을 기록해야 합니다. decision
record는 각 accepted claim ID 또는 전체 claim 내용을 참조해야 합니다. 기존
프로젝트 migration은 현재 gate가 갑자기 닫히지 않도록 `require_claim_matrix: false`를
유지하며 matrix 작성 후 명시적으로 활성화합니다.

신규 프로젝트는 `require_decision_snapshot: true`도 사용합니다. `decision-draft`는
현재 증거, claim과 증거 정책의 SHA-256 digest를 기록합니다. 이 입력 중 하나라도
변경되면 결정문을 검토하고 다시 생성할 때까지 coder와 reviewer gate가 닫힙니다.
기존 프로젝트 migration에서는 엄격한 무효화 절차를 준비할 때까지 이 설정을
비활성화합니다.

프로젝트 테스트 전에 승인할 정확한 명령을
`workspace/verification-policy.json`에 등록합니다. `verification-plan`은 실행
없이 허용 여부를 확인하고, `verification-run`은 의사결정 gate가 열린 경우에만
명령을 실행해 결과를 `workspace/verifications/latest.json`에 저장합니다.
정책 비교는 parsing된 인자를 사용하므로 따옴표 내부 공백까지 정확히 일치해야 하며
shell operator와 제어문자를 거부합니다. bare Python launcher는 현재 runtime을
사용하고 명시한 interpreter 경로는 유지합니다. Windows와 POSIX의 공백 포함
경로를 지원합니다.

AI가 만든 unified diff는 `patch-plan`으로 먼저 검사합니다.
`workspace/repair-policy.json`이 수정 가능 경로와 크기를 제한합니다. 적용된
patch는 원본 백업을 남기며, 이후 사용자 변경이 있으면 rollback을 거부합니다.
diff header는 slash와 Windows 구분자를 모두 허용하고 LF·CRLF diff를 처리하되
기존 대상 파일의 줄바꿈 형식을 보존합니다.

`archive`는 검사 가능한 프로젝트 ZIP을 만듭니다. 생성 전에
`workspace/archive-policy.json`의 파일 수, 개별 크기와 전체 크기 제한을 모두
검사합니다. symlink, 이전 archive, VCS metadata, bytecode, `.env`, key와 인증서
파일은 기본 제외되며 정책 실패 시 부분 ZIP을 남기지 않습니다.
각 archive에는 SHA-256 파일 목록이 포함됩니다. 최신 archive는
`archive-verify`로, 특정 ZIP은 `archive-verify --file PATH`로 검사합니다.
압축을 풀지 않고 누락, 추가, 변경, 중복 및 위험 경로를 탐지합니다.

`audit-check`는 모든 JSONL 기록, timestamp와 SHA-256 record chain을 검사합니다.
첫 version-2 event는 기존 legacy 기록을 anchor로 묶고 이후 event는 유효한 JSON의
변경, 삽입, 삭제와 순서 변경을 탐지합니다. 이 체인은 일관성 검사용이며, 파일과 hash를
모두 다시 쓸 수 있는 주체를 막는 전자서명은 아닙니다. `audit-export`는
전체 이력, event 집계와 검증 결과를 `workspace/reports/`에 저장합니다. 파일명은
`--filename NAME.json`으로 지정할 수 있습니다.
qualification은 audit summary만 포함하며 malformed row, 필수 field 누락, 잘못된
timestamp가 있으면 readiness를 차단합니다. event record 본문은 보고서에 넣지 않습니다.
qualification은 scorecard root와 boolean check도 검사합니다. 손상된 scorecard는
덮어쓰지 않고 본문을 노출하지 않은 오류만 보고합니다.

`repair-run`은 debugger 진단, coder patch 생성, 안전한 적용, 재검증과 독립
reviewer 판정을 제한된 횟수만큼 수행합니다. 실패하거나 거절된 patch는 기본적으로
복원됩니다. `repair-status`로 checkpoint를 확인하며, `repair-resume`은 저장된
patch hash를 검사한 뒤 debugger, diff, patch, 검증 또는 reviewer 중 마지막으로
완료한 단계 다음부터 이어갑니다. 완료된 AI 호출은 반복하지 않으며 기존 시간과
AI 호출 사용량도 budget에 유지됩니다. 실패하거나 거절된 작업만 복원한 뒤 남은
시도 횟수를 연결된 세션에 전달하며, 사용자 파일 변경이 있으면 재개를 차단합니다.
format-v2 repair session은 durable 저장마다 session 전체 SHA-256을 갱신합니다.
task metadata, budget, attempts, verification, patch·rollback 기록, 실제 service
identity와 reviewer 데이터를 함께 묶습니다. canonical 로더는 identity, status,
attempt 순서, 승인 review provenance와 hash를 resume, 과거 `runs`, qualification에서
검사하며 format-v1은 계속 읽을 수 있습니다.

### 한 번의 명령으로 구현 및 마무리

결정 게이트가 열리고 `verification-plan`이 승인된 이후 다음 명령을 실행합니다.

```powershell
.\run.ps1 implement --task "승인된 변경 구현"
```

이 명령은 coder diff 생성과 hunk 줄 수 보정, 경로 검증, 스냅샷 생성, 패치 적용,
승인된 테스트와 qualification 실행을 처리합니다. 실패한 패치는 자동으로 롤백하고,
성공하면 archive 생성과 무결성 검증까지 완료합니다. 코드가 이미 적용된 프로젝트는
다음 명령만 실행합니다.

```powershell
.\run.ps1 finish
```

`workspace/repair-policy.json`의 `max_elapsed_seconds`, `max_ai_calls`,
`ai_max_tokens`는 전체 경과 시간, AI 호출 수와 호출별 생성 token을 제한합니다.
한도를 소진하면 `budget_exhausted` terminal 세션으로 기록하고 활성 patch를
안전하게 복원한 뒤 중단합니다.

`debate-rounds`는 이전 라운드의 주장을 다음 라운드에 전달합니다.
decision-maker는 decision, rationale, agreements, disagreements, risks와
confidence, implementation brief, 제안 verification commands를 포함한 JSON
판정을 반환해야 합니다. verdict는 정규화된 SHA-256과 함께 저장됩니다.
`decision-draft`는 hash를 검증한 뒤 accepted decision과 coder brief에 반영하며,
변조된 verdict는 초안 생성을 차단합니다. 제안 명령은 여전히
`workspace/verification-policy.json`의 정확한 승인이 필요합니다. 동일한 성공 AI
호출은 정책에 따라 `workspace/cache/ai/`에서 재사용됩니다.
debate 보고서는 verdict를 현재 evidence·claim·정책 digest에 결속합니다.
`claim_ids`는 accepted 구조화 claim만 참조해야 하며 claim matrix가 필수이고
유효하면 모든 accepted claim을 포함해야 합니다. 검증 지식이 변경되면 verdict는
stale 상태가 되므로 결정문 작성 전에 `debate-rounds`를 다시 실행합니다.
각 multi-round debate는 durable 세션을 가집니다. `debate-status`로 현재 round,
연결 pipeline, 완료 round와 judge 단계를 확인합니다. `debate-resume`은 완료 round를
반복하지 않고 실패 pipeline 또는 judge만 이어갑니다. 판정 전에 evidence가 바뀌면
세션은 terminal `stale` 상태가 됩니다. 미해결 또는 손상된 최신 debate 세션은
`qualify` readiness를 차단합니다.
format-v3 debate session은 각 round의 role-output provenance 전체를 hash로
검증합니다. format-v2 최종 report는 verdict, rounds, 실제 service independence,
participant와 judge identity를 하나의 결과 hash로 묶습니다. resume, 과거 `runs`,
qualification이 canonical 검증을 사용하며 기존 format-v2 session도 호환됩니다.
같은 orchestration 정책의 `max_debate_rounds`, `max_debate_elapsed_seconds`,
`max_debate_ai_calls`는 debate 전체의 round, 경과 시간과 AI 호출을 제한합니다.
각 round는 실행 전에 모든 역할 호출을, judge는 시도마다 한 호출을 예약합니다.
저장된 사용량은 `debate-resume`에서 복원되며 한도 소진은 terminal
`budget_exhausted` 상태로 기록되어 `qualify`를 차단합니다.
실패, stale 또는 미완료 세션을 의도적으로 대체했다면 사유와 함께
`debate-abandon`을 사용합니다. 폐기는 감사 로그에 기록되고 qualification 상태를
해결하지만 완료로 가장하지 않으며, 폐기한 세션은 다시 재개할 수 없습니다.
debate 전체 예산 필드가 없는 구형 체크포인트도 원본 hash가 유효하면 로드할 때
새 형식으로 변환합니다. 완료 round와 이미 시도한 judge 호출은 복원 예산에
보수적으로 반영하며, 형식이 잘못됐거나 hash가 다른 구형 세션은 거부합니다.
runtime checkpoint는 같은 디렉터리의 임시 파일을 flush한 뒤 파일별 lock 안에서
atomic replace합니다. audit append, scorecard 갱신, evidence와 claim 변경도
직렬화됩니다. 같은 pipeline, debate 또는 repair 세션의 resume·abandon 명령은
동시에 실행되지 않습니다. 활성 소유자가 있으면 `already active` 오류를 반환하고,
종료된 프로세스가 남긴 lock은 자동 회수합니다.
기존 mutable JSON이 손상되었거나 object root가 아니면 갱신은 fail-closed로
중단됩니다. 오류는 path와 parse 위치만 표시하고 state·scorecard 원본 byte는
복구를 위해 그대로 보존합니다.
두 atomic write 사이에서 프로세스가 중단되어 복제된 `latest` checkpoint가 없거나
오래된 경우에는 `updated_at`이 가장 최신인 원본 세션을 선택합니다. 따라서
qualification도 중단된 작업을 `not_started`로 숨기지 않고 현재 상태로 보고합니다.
각 pipeline 역할은 provider 호출 전에 in-flight 예약을 기록하고, 출력 계약을
통과한 성공 응답을 역할 checkpoint보다 먼저 cache합니다. 그 사이에 중단되면
추가 provider 호출이나 AI 호출 예산 차감 없이 cache에서 재개합니다. 출력 크기
계약에 거절된 응답은 cache하지 않습니다. 역할, prompt, routing, 생성 설정이 같은
동시 요청은 cache key별 single-flight로 처리합니다. 잠금 소유자만 provider를
호출하고 대기 작업은 저장된 성공 응답을 재사용하되 각 pipeline의 논리적 AI 호출
예산 기록은 그대로 유지합니다.
cache format v2는 provider 별칭과 동등 URL을 canonicalize합니다. 활성 상태, 설정
유효성 또는 API key 값이 바뀌면 기존 cache를 재사용하지 않습니다. credential
fingerprint는 최종 cache key 계산에만 쓰며 cache 본문이나 audit에 저장하지 않습니다.
각 entry의 `result_sha256`은 파일 key, role, 응답, service metadata와 diagnostics를
결합합니다. 변경되거나 이름이 바뀐 entry는 재생하지 않고 `invalid`로 분류합니다.
`ai-cache-status`는 prompt나 응답 본문을 노출하지 않고 fresh, stale, 손상 항목
수와 전체 크기만 보여줍니다. `ai-cache-prune`은 cache key 잠금 아래 만료·손상
항목을 제거하며, `--all`을 지정한 경우에만 fresh 항목도 제거합니다.

`invoke --json`은 primary와 fallback의 시도, 소요 시간, HTTP 상태, 재시도 가능
여부와 오류 분류를 민감정보 없이 출력합니다. pipeline 실행 파일과 cache hit에도
같은 진단이 유지됩니다. prompt, 응답 본문, credential, URL 사용자 정보와 query
문자열은 진단 및 감사 event에 포함하지 않습니다.

각 pipeline에는 실행 ID가 부여되며 세션과 역할별 결과가
`workspace/executions/runs/`에 보존됩니다. `pipeline-status`로 checkpoint를
확인합니다. 역할 실행이 실패하면 `pipeline-resume`이 저장 결과로 context를
복원하고 첫 미완료 역할부터 이어갑니다. 완료된 AI 호출은 반복하지 않으며,
완료 pipeline을 다시 재개해도 provider를 호출하지 않고 기록 결과를 반환합니다.
format-v2 pipeline checkpoint는 service identity, diagnostics, content와 context
metadata를 포함한 role 결과 전체 provenance를 hash로 검증합니다. 로더는 session
identity, 입력, status, 순서와 completed 결과 수도 검사합니다. 과거 `runs`와
qualification도 같은 검증을 사용하며 format-v1은 기존 content hash와 호환됩니다.
`workspace/orchestration-policy.json`은 역할 수, prompt와 system 길이, 전달
context, 전체 경과 시간과 누적 AI 호출 수를 제한합니다. 제한과 사용량은 세션에
저장됩니다. provider 호출 전에 AI 호출 예산을 예약하므로 프로세스 중단으로 이미
쓴 예산이 복원되지 않습니다. 예산 소진은 terminal 상태이며 오래된 역할 결과는
context 최대치를 넘기 전에 생략하거나 잘라냅니다.
`min_output_chars`와 `max_output_chars`는 비어 있지는 않지만 사용할 수 없을 만큼
짧거나 과도하게 큰 응답이 다음 역할로 전달되는 것을 막습니다. 거절된 응답도 예약한
AI 호출 예산을 사용하며, 같은 역할을 미완료 상태로 남겨 명시적으로 재개할 수 있습니다.
`qualify`는 정책 유효성과 최신 checkpoint를 함께 검사합니다. 미해결 또는 손상 실행은
readiness를 차단합니다. 실행이 의도적으로 대체되었다면 `pipeline-abandon`에 사유를
기록해 완료로 가장하지 않으면서 감사 가능한 해결 상태로 닫습니다.

`role-plan`은 한글과 영어 작업 신호를 결정론적으로 분류해 정방향 역할 순서를
추천합니다. 누락되거나 비활성화된 service를 표시하고 decision gate가 닫혀 있으면
coder/reviewer를 차단합니다. 계획은 `workspace/orchestration/`에 저장되지만 AI를
호출하거나 작업을 실행하지 않습니다.
`orchestrate`는 이 계획에서 검증된 한 단계를 실행합니다. `planning`은 정방향
pipeline, `debate`는 planning 참가자와 별도 decision-maker judge, `repair`는
debugger·coder·verification·reviewer loop를 실행합니다. 필수 service와 decision
gate blocker는 provider 호출 전에 실패하며, 각 단계는 기존 checkpoint·budget·
resume·rollback 규칙을 그대로 사용합니다.
Wrapper는 `workspace/orchestration/executions/`에 본문을 제거한 실행 checkpoint를
저장해 plan ID와 task hash를 하위 session에 연결합니다. `orchestrate-status`로
task나 AI 출력 본문을 노출하지 않고 성공·실패 wrapper를 확인할 수 있습니다.
format-v2 plan과 wrapper는 각각 저장된 provenance 전체를 hash로 검증합니다. wrapper는
plan hash와 본문을 제거한 task hash를 원본 plan에 결합합니다. canonical loader는 stage, 하위 session
identity, 종료 상태 일관성도 검사합니다. 과거 `runs`와 qualification도 같은 loader를
사용하므로 완료 wrapper가 변조되면 숨겨지지 않고 `invalid_checkpoint`로 보고됩니다.
plan loader는 task에서 tag와 권장·planning 역할을 다시 도출합니다. hash를 다시
계산한 경우에도 role·service snapshot, blocker 요약, 실행 가능 flag, decision gate
구조와 제한된 command template의 내부 일관성을 검증합니다.
blocker는 service 할당·활성 flag와 gate 상태에서 다시 계산하고, 정확한 command 순서는
task tag와 planning 역할에서 다시 생성합니다.
wrapper 역할 순서는 저장 plan과 stage에서 도출한 역할과 정확히 같아야 합니다.
round·retry·repair attempt 옵션은 범위와 타입을 plan 생성 전과 format-v2 wrapper를
불러올 때마다 검증합니다.
하위 pipeline·debate·repair ID는 단계 실행 전에 예약·저장되므로 hard interruption
후에도 wrapper checkpoint에 복구 대상 ID가 남습니다.
예약 ID는 wrapper ID와 task hash에서 결정적으로 생성됩니다. wrapper hash를 다시
계산해도 다른 하위 ID 연결은 거부하며, stage engine이 다른 ID를 반환하면 복구 가능한
canonical failed wrapper로 기록합니다.
하위 상태는 해당 durable engine이 생성하는 상태로 제한하며 wrapper-child 수명주기도
일관되어야 합니다. 예를 들어 running wrapper가 completed child를 주장하거나 abandoned
wrapper가 active child를 가리키는 조합은 거부됩니다.
wrapper 수명주기 시각은 timezone을 포함하고 단조 증가해야 합니다. running·completed는
오류를 포함할 수 없고 failed는 오류가 필수이며, abandoned는 제한된 사유와 수명주기
범위 안의 abandon 시각이 필요합니다.
`orchestrate-resume`은 저장 plan identity와 task hash를 검증한 뒤 기존 하위
checkpoint를 재개합니다. 하위 session 생성 전 중단된 경우에는 같은 예약 ID로
단계를 시작하며, 완료 후 반복 실행해도 provider를 호출하지 않습니다.
`orchestrate-reconcile`은 하위 작업을 계속 실행하거나 provider를 호출하지 않고
하위 checkpoint 상태를 wrapper에 반영합니다. 하위 작업 완료와 wrapper 갱신 사이의
중단으로 생긴 상태 불일치를 복구할 때 사용합니다.
`orchestrate-reconcile-all`은 같은 복구를 제한된 개수의 wrapper에 일괄 적용하며,
실행 중이거나 하위 checkpoint가 없는 wrapper는 건너뜁니다.
wrapper 완료는 planning·debate의 completed 또는 repair의 approved·already_verified
상태에서만 인정합니다. 하위 명령이 정상 반환했더라도 시도·예산 소진 등 성공하지
못한 종료 결과는 wrapper를 failed 상태로 유지합니다.
`orchestrate`와 `orchestrate-resume`은 wrapper가 completed일 때만 종료 코드 `0`을
반환합니다. 기록된 비성공 결과는 `2`, 호출·검증 예외는 `1`을 반환합니다.
`orchestrate-reconcile`도 같은 wrapper 계약을 사용합니다. `repair-run`과
`repair-resume`은 `approved` 또는 `already_verified`일 때만 `0`, 저장된 비성공
종료 상태에는 `2`를 반환합니다. reconcile-all의 wrapper 검사 실패는 `1`입니다.
repair는 reviewer 호출 전과 최종 승인 기록 직전에 현재 decision gate를 다시
검사합니다. 시도 중 evidence·claim·decision이 바뀌면 오래된 승인을 차단하고,
적용된 patch는 정책에 따른 rollback 경로로 처리합니다.
중단 직전에 저장된 approved verdict도 그대로 신뢰하지 않습니다. resume 시 gate를
재검증하고 오래된 승인을 명시적으로 표시한 뒤 적용된 patch를 rollback합니다.
미해결 wrapper는 `runs --unresolved`와 qualification 이력에 포함됩니다. 이 보고서는
하위 checkpoint 상태에 따라 reconcile·resume·abandon 중 안전한 다음 명령을 제안합니다. 대체된
wrapper는 사유와 함께 `orchestrate-abandon`으로 닫습니다. 연결된
pipeline·debate·repair checkpoint가 있으면 하위 session을 먼저 abandon합니다.
하위 정리나 repair rollback이 실패하면 wrapper는 미해결 상태로 유지됩니다.
이력 검증은 terminal wrapper 링크도 따라갑니다. completed wrapper는 canonical child
checkpoint가 반드시 존재해야 합니다. abandoned wrapper는 child가 `not_started`인
경우에만 파일이 없어도 되며, 그 외에는 저장 child 상태와 실제 canonical 상태가
같아야 합니다.
wrapper task hash는 canonical pipeline·debate prompt hash 또는 repair task hash와도
같아야 합니다. 다른 task에서 생성한 정상 child를 예상 경로에 놓아도 terminal
wrapper를 충족할 수 없습니다.
pipeline·debate child 역할 순서는 wrapper 역할 계약과 같아야 합니다. planning
pipeline은 고정된 evidence-aware system prompt를 사용해야 하며 pipeline·debate의
retry 옵션도 저장 wrapper 옵션과 일치해야 합니다.
debate round는 두 checkpoint를 만들기 전에 policy로 제한하여 wrapper와 child가 같은
effective 값을 저장합니다. terminal debate round는 정확히 일치해야 하며 repair attempt
한도는 유효하고 명시적인 wrapper 요청을 넘을 수 없습니다.

## 현재 범위

명시한 원문 URL을 안전하게 수집할 수 있으며, self-hosted SearXNG를 통해 승인 전
후보를 선택적으로 발견할 수 있습니다. 안전한 patch 처리와 제한된 AI 수정
orchestration은 구현되어 있습니다. 실제 provider 종단간 검증과 추가 검색
provider가 다음 개발 우선순위입니다.
