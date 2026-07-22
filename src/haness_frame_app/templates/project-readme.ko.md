# $project_name

생성 시각: $created_at

## 개요

이 폴더는 문서 템플릿만이 아니라 실제로 실행할 수 있는 하네스 엔지니어링
프로젝트입니다. 프로젝트 문서, 역할 라우팅, evidence, 결정 gate, 패치 적용,
테스트, qualification과 archive 기능을 포함합니다.

기본 영문 설명은 `README.md`에 있습니다.

## 작업 설명

$working_description

## 빠른 상태 확인

```powershell
.\run.ps1 summary
.\run.ps1 check
.\run.ps1 live-check --role planner
```

AI 서비스 설정은 `workspace/services.json`에서 관리합니다.

## 한 줄 구현

결정 gate가 열리고 `verification-plan`이 승인된 이후 실행합니다.

```powershell
.\run.ps1 implement --task "승인된 기능 구현"
```

이 명령은 coder diff 생성, hunk 줄 수 보정, 경로 검증, 스냅샷, 패치 적용,
승인된 테스트, qualification, archive 생성과 무결성 검사를 수행합니다. 실패한
패치는 자동으로 롤백합니다.

코드가 이미 적용된 경우 최종 검증만 실행합니다.

```powershell
.\run.ps1 finish
```

## 엄격한 작업 흐름

1. `context/business-context.md`에서 범위와 제약을 확인합니다.
2. `research/search-backlog.md`의 조사 항목을 검토합니다.
3. 구조화된 evidence와 claim을 기록합니다.
4. 역할 토론 결과를 `docs/03-decision-record.md`에 반영합니다.
5. `python app.py gate`가 허용 상태인지 확인합니다.
6. 승인된 구현과 테스트를 실행합니다.
7. qualification과 archive 무결성을 확인합니다.

주요 명령:

```powershell
.\run.ps1 summary
.\run.ps1 evidence-check
.\run.ps1 claim-check
.\run.ps1 debate-status --id latest
.\run.ps1 decision-draft
.\run.ps1 gate
.\run.ps1 verification-plan
.\run.ps1 runs --unresolved
```

## 프로젝트 폴더

```text
context/          프로젝트 목적과 내부 문맥
research/         검색 계획과 외부 evidence
docs/             발견, 토론과 결정 기록
prompts/          역할별 prompt
implementation/  구현 결과와 작업 기록
tests/            생성된 테스트
workspace/        정책, 상태, 실행 기록과 archive
src/              프로젝트에 포함된 하네스 실행 엔진
```

## 실패 복구

```powershell
.\run.ps1 runs --unresolved
.\run.ps1 repair-status --id latest
.\run.ps1 repair-resume --id SESSION_ID --retries 0
```

사용자 파일이 변경됐거나 작업이 대체된 경우에는 무조건 덮어쓰지 않고 복구 또는
명시적인 abandon 절차를 사용합니다.
