# 테스트 절차

## 테스트 계층

1. `python -m compileall src`로 본체 source를 compile합니다.
2. `python scripts\sync_generated_projects.py`로 생성 프로젝트 runtime을 동기화합니다.
3. 전체 unit·integration suite를 `python -m unittest discover -s tests -q`로 실행합니다.
4. 새 프로젝트 생성 E2E에서 manifest와 기본 gate 수명주기를 검증합니다.
5. gate가 닫힌 프로젝트와 열린 프로젝트에서 verification 차단·실행을 검증합니다.
6. 허용되지 않은 명령, shell 연산자, 시간 초과와 출력 제한을 검증합니다.
7. patch 경로 이탈, context 불일치, 사용자 후속 변경과 rollback 충돌을 검증합니다.
8. pipeline 실패 역할 재개, 호출 budget, 멱등 완료와 abandon을 process 단위로 검증합니다.
9. debate round, judge 실패 재개, verdict, decision gate와 stale evidence를 검증합니다.
10. repair에서 실패 테스트, 진단, diff, 재검증, reviewer 승인과 rollback을 검증합니다.
11. 직접 URL evidence의 사설망·domain·redirect·content type·크기 제한을 검증합니다.
12. evidence fingerprint, claim matrix, decision snapshot과 오래된 승인 차단을 검증합니다.
13. OpenAI-compatible·Ollama adapter와 fallback 계약을 결정론적 HTTP fixture로 검증합니다.
14. 동일 AI 요청의 single-flight cache와 본문 비노출 cache 관리를 검증합니다.
15. snapshot·archive·audit chain·scorecard·manifest 손상 감지를 검증합니다.
16. pipeline·debate·repair·orchestration checkpoint 변조와 이력 qualification을 검증합니다.
17. Golden E2E에서 하나의 생성 프로젝트로 evidence → claim → debate → decision →
    gate → repair → test → review → qualification 전체 흐름을 실행합니다.

## 필수 명령

```powershell
python scripts\sync_generated_projects.py
python -m unittest discover -s tests -q
python -m compileall -q src tests scripts projects\finish-smoke\src
git diff --check
```

핵심 process 흐름만 빠르게 재검증할 때는 다음 테스트를 실행합니다.

```powershell
python -m unittest tests.test_golden_harness_e2e `
  tests.test_project_generation_e2e `
  tests.test_pipeline_process_e2e `
  tests.test_debate_decision_process_e2e `
  tests.test_repair_process_e2e -v
```

## 기대 결과

- evidence와 accepted decision이 없으면 coder와 reviewer 실행이 차단됩니다.
- 구조화 evidence, accepted claim과 최신 decision snapshot이 gate를 엽니다.
- AI 토론 결과는 별도 decision-maker verdict를 거쳐 decision 문서로 연결됩니다.
- 허용 경로 안의 patch만 적용되고 선언된 verification이 자동 실행됩니다.
- verification 실패나 reviewer 거부는 승인되지 않으며 정책에 따라 rollback됩니다.
- 중단된 pipeline·debate·repair는 완료 작업을 반복하지 않고 재개됩니다.
- 손상되거나 서로 불일치하는 checkpoint는 `runs --unresolved`와 qualification에서 차단됩니다.
- Golden E2E의 최종 `qualify --run-verification`이 성공합니다.
- runtime module이 compile되고 생성 manifest의 모든 항목이 존재합니다.
- audit, cache, session overview는 prompt·AI 응답 본문을 불필요하게 노출하지 않습니다.

## 환경 의존 선택 테스트

실제 로컬 provider가 실행 중인 환경에서는
`python app.py live-check --role planner`로 service probe와 live invoke를 수행합니다.
이 명령은 응답 본문 없이 길이와 SHA-256만 JSON으로 보고하며 실패하면 비정상 종료합니다.
이 검증은 모델의 설치·가용성에 의존하므로 기본 자동 suite에서는 강제하지 않습니다.
이번 릴리스에는 모델별 튜닝과 vLLM 설정 작업을 포함하지 않습니다.
