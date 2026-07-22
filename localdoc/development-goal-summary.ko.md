# 개발 목표와 현재 상태

## 목표

로컬 AI 사용자가 전문 역할을 연결하고, 추적 가능한 증거로 지식을 검증하며,
코딩 전에 의사결정을 확정하고, 안전한 한도 안에서 구현·테스트·진단·수정을
반복하여 정상 동작하는 프로그램을 쉽게 만들도록 지원합니다. 클라우드 AI는
필수가 아니라 선택 가능한 확장 경로입니다.

## 사용자 결과

사용자는 만들 프로그램이나 변경 사항을 설명하고 로컬 AI 모델을 연결한 뒤,
증거, 의사결정, diff, 테스트 결과와 남은 위험을 포함한 검증 결과를 받아야
합니다.

## 구현 완료

- 프로젝트 생성과 역할별 AI 서비스 라우팅
- AI 호출, 재시도와 fallback 라우팅
- 순차 pipeline과 구조화된 다중 라운드 설계 토론
- 검색 계획, 구조화된 증거 기록과 증거 품질 정책
- 사설망 보호가 적용된 정책 기반 직접 URL 증거 수집
- 의사결정 초안과 coder/reviewer gate 강제
- 정책 승인 명령만 실행하는 시간·출력 제한 검증기
- unified diff 검증, 적용, 백업과 충돌 방지 rollback
- debugger, coder, 검증, reviewer 기반의 제한된 수정 루프
- checkpoint 조회와 충돌 방지 수정 세션 복구
- 정확한 입력 기반 AI 응답 cache
- hash 검증 debate verdict의 결정문·coder brief 연계
- debate verdict의 evidence snapshot·accepted claim 최신성 검증
- CLI·HTTP debate→decision gate와 stale evidence 차단 종단 간 검증
- durable debate round·judge checkpoint와 qualification 통합 멱등 재개
- debate 전체 round·경과 시간·AI 호출 예산과 terminal 소진 처리
- 대체된 debate 세션의 감사 가능한 폐기와 qualification 해결 상태
- 예산 도입 전 debate checkpoint의 hash 검증 migration과 보수적 사용량 복원
- atomic runtime 저장과 프로세스 간 세션·데이터 lock 및 종료 소유자 복구
- 손상 원본을 보존하는 state·scorecard fail-closed mutation
- fail-closed manifest schema와 프로젝트 경계 경로 검증
- 손상 원본을 보존하는 evidence·search-plan fail-closed loading
- latest checkpoint pointer 갱신 실패 시 durable 원본 세션 자동 복구
- provider 응답과 역할 checkpoint 사이 중단 시 pipeline 성공 cache 복구
- 동일 AI 요청 동시 실행을 cache key별 하나의 provider 호출로 통합
- 본문을 노출하지 않는 cache 상태 확인과 잠금 기반 만료·손상 cache 정리
- 설정·credential 변경을 반영하는 canonical AI cache identity
- cache 재생 전 결과·파일 key 무결성 검증
- pipeline·debate·repair 미해결 session 통합 현황과 안전한 복구 명령
- qualification 통합 repair 상태 검사와 rollback-safe 감사 가능 abandon
- 전체 durable session 이력 qualification과 repair successor 명시적 인계
- 직접 evidence 원문 fingerprint와 본문 비저장 변경 재검증
- 원문 변경 qualification 차단과 검토 기반 evidence refresh·decision 무효화
- 정책 제한 일괄 원문 재검증과 부분 실패 전체 집계
- gate-aware 결정론적 planning·debate·repair 단계 실행
- 본문 비저장 orchestration 실행 checkpoint와 단계 session 연결
- qualification 통합 orchestration wrapper 수명주기와 감사 가능 abandon
- hard interruption 복구를 위한 실행 전 하위 session ID 예약
- 하위 session 생성 경계 전후 hash 검증 orchestration 재개
- provider 호출 없는 하위 session 기반 wrapper 상태 정합화
- 종료된 하위 session의 제한형 일괄 wrapper 정합화
- 단계별 하위 성공 상태 기반 wrapper 완료 판정
- CI 안전 orchestration 종료 코드와 비정상 결과 감사 이벤트
- reviewer 경계 gate 재검증과 오래된 승인 방지
- 재개 시 저장 승인 무효화와 적용 patch rollback
- coder/reviewer 서비스 identity 독립성 진단
- 선택형 엄격 독립 reviewer qualification·repair 정책
- 승인 전 fallback·cache 실제 coder/reviewer identity 강제
- qualification 시 durable 승인 repair 실제 identity 재검증
- 실제 review identity·verdict SHA-256 provenance 결합
- 설정·실제 debate judge 독립성 강제와 provenance 검증
- 설정 judge 독립성 경고와 엄격 정책의 토론 전 qualification 차단
- 하위 session 우선 orchestration abandon과 rollback 실패 보호
- 감사 로그, scorecard, manifest, snapshot과 archive
- 영어와 한국어 운영 문서
- OpenAI 호환, Ollama와 fallback 경로의 결정론적 HTTP 통합 테스트
- 실패 테스트, AI patch, 재검증과 reviewer 승인의 process 단위 검증
- 경과 시간, AI 호출과 생성 token을 제한하는 수정 예산
- 프로젝트 준비 상태와 실행 검증을 구분하는 통합 qualification 보고서
- 증거 승인과 분리된 선택적 self-hosted SearXNG 후보 검색
- 비밀 파일과 symlink를 제외하는 정책 사전 검사 기반 프로젝트 archive
- archive 내부 SHA-256 목록과 압축 해제 없는 무결성 검증
- 엄격한 감사 로그 검사와 프로젝트 경계 내 JSON 이력 export
- legacy 이력을 anchor로 묶고 기록 변경을 탐지하는 append-only SHA-256 감사 체인
- qualification 통합 본문 비노출 audit health
- 손상 본문을 노출하거나 덮어쓰지 않는 qualification 통합 scorecard health
- authoritative evidence JSON과 파생 Markdown 불일치 탐지 및 결정적 재생성
- CI 대상 검사 명령 전체의 일관된 성공·실패 프로세스 종료 코드
- repair와 orchestration 복구 명령의 durable 상태 기반 프로세스 종료 코드
- format-v2 pipeline provenance hash와 과거 checkpoint canonical 검증
- format-v3 debate round·최종 결과 provenance와 과거 checkpoint canonical 검증
- format-v2 repair 전체 session provenance와 저장·재개·이력·qualification 검증
- format-v2 orchestration plan/wrapper 전체 provenance와 checkpoint 상호 결합·과거 이력 canonical 검증
- plan-stage 역할 결합과 orchestration 옵션의 타입·범위 검증
- 결정적 wrapper-child 예약 결합과 ID 불일치의 durable 실패 처리
- stage별 child 상태 허용 목록과 wrapper-child 수명주기 일관성 검증
- wrapper 시각 단조성 및 상태별 오류·abandon 메타데이터 검증
- plan 의미 재도출과 role·blocker·gate·service·command 구조 검증
- service·gate·tag·role 입력 기반 plan blocker와 command 결정적 재생성
- 이력·qualification의 terminal wrapper-child 존재 및 canonical 상태 검증
- canonical checkpoint 간 terminal wrapper-child task 입력 hash 결합
- terminal wrapper-child 역할·planning system·retry 계약 검증
- policy effective debate round와 제한된 repair attempt wrapper-child 계약
- hash 검증 기반 단계별 수정 재개와 시간·AI 호출 예산 복원
- 민감정보를 제거한 provider 시도·재시도·fallback·시간·오류 진단
- provider별 live probe와 설정 모델 존재 여부 검증
- adapter 별칭과 동등 URL 우회를 막는 canonical service identity
- primary·fallback 공용 사전 검증과 자격증명 안전 URL 진단
- fallback 설정 오류를 숨기지 않는 canonical route 중복 제거
- 진단·호출·qualification 전반의 손상 service snapshot 명시적 처리
- 생성 프로젝트 role contract의 service 할당 완전성 강제
- state·service 역할 할당 snapshot 일관성 강제
- 교차 플랫폼 명령 인자 정책과 LF·CRLF patch 호환 fixture
- 결정론적 한영 작업 분류와 gate 인식 역할 계획
- 실행별 pipeline checkpoint와 첫 미완료 역할부터 이어지는 멱등 재개
- 저장되는 pipeline 역할·context·경과 시간·누적 AI 호출 예산
- 역할 출력 크기 계약과 CLI·HTTP 실패 역할 재개 검증
- qualification 통합 pipeline 상태 검사와 명시적 감사 가능 abandon
- 증거 연결 claim matrix, 반론 해소와 decision 참조 검증
- 증거·claim·증거 정책 변경 시 오래된 승인을 차단하는 SHA-256 결정 입력 스냅샷
- 프로젝트 생성부터 증거·claim 검증, 결정문 작성과 gate 개방까지의
  전체 수명주기 자동 테스트

## 다음 우선순위

- 추가 검색 provider와 더 정교한 출처 검증
- 실제 provider를 사용한 토론과 수정 품질 검증
- 실제 provider 종단 간 qualification과 더 세밀한 단계별 멱등성
- 재개, timeout, 예산, 보안과 관측성 제어 강화

## 완료 기준

- coder와 reviewer가 증거 및 의사결정 gate를 우회할 수 없습니다.
- 생성 patch는 선택한 프로젝트의 허용 경로 안에서만 적용됩니다.
- 선언된 테스트가 patch 적용 후 자동으로 실행됩니다.
- 실패 원인을 집중 진단하고 제한된 횟수만 수정합니다.
- 독립 reviewer가 테스트된 결과의 승인 여부를 결정합니다.
- 중단된 실행을 안전하게 재개하고 모든 주요 산출물을 감사할 수 있습니다.
