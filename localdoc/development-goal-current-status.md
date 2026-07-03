# haness-frame 개발 목표와 현재 진행 상태

> 기준일: 2026-07-03

## 1. 개발 목표

haness-frame의 목표는 로컬 멀티 모델 코드 하니스로서,
프로젝트 생성부터 역할 분리, 검색 증거 수집, 의사결정 게이트,
실행 로그와 스냅샷/아카이브까지 한 흐름으로 다루는 것입니다.

핵심은 다음과 같습니다.

- Planner, Coder, Reviewer, Researcher 등 역할을 분리한다.
- 프로젝트별 작업공간을 생성한다.
- 검색 증거와 의사결정 기록을 구조화한다.
- 모델 호출, 파이프라인, 검증, 로그, 백업을 하나의 하니스로 묶는다.
- 생성된 프로젝트가 독립적으로 실행 가능해야 한다.

## 2. 현재 개발 중인 것

현재 개발은 `work/haness-frame` 복사본 기준으로 진행 중입니다.

### 2.1 하니스 생성기

- `src/haness_frame_app/project_docs.py`
- 프로젝트 파일 조립과 생성 템플릿 로딩을 담당한다.
- 현재는 500라인 미만으로 유지하면서, 생성 런타임 코드는 별도 템플릿 파일에서 읽는다.

### 2.2 런타임 템플릿

`src/haness_frame_app/templates/runtime/` 아래로 생성될 프로젝트 코드가 분리되어 있다.

현재 포함된 런타임 모듈:

- `cli.py`
- `engine.py`
- `workflow.py`
- `client.py`
- `evidence.py`
- `scorecard.py`
- `audit.py`
- `manifest.py`
- `snapshots.py`
- `search.py`
- `debate.py`
- `archive.py`

### 2.3 현재 구현된 기능

- 프로젝트 생성 웹 UI
- 프로젝트 파일 생성
- 프로젝트 로컬 `invoke`
- 역할 기반 `pipeline`
- 검색 증거 추가와 검색 계획 생성
- 의사결정 게이트 검사
- 실행 로그 기록
- scorecard 갱신
- manifest 검증
- snapshot / rollback 경로
- debate 실행 경로
- archive 생성
- verify 검증 명령

## 3. 현재 검증된 상태

생성된 프로젝트에서 다음을 확인했다.

- `python -m compileall src`
- `python app.py manifest`
- `python app.py search-plan`
- `python app.py add-evidence ...`
- `python app.py snapshot --label ...`
- `python app.py archive --label ...`
- `python app.py verify`

확인 결과:

- manifest는 유효하다.
- 검색 계획은 8개 쿼리로 생성된다.
- 구조화된 evidence 기록이 scorecard에 반영된다.
- snapshot과 archive 파일이 실제로 생성된다.
- verify는 compileall과 manifest, decision gate를 함께 점검한다.

## 4. 아직 남아 있는 일

현재 남아 있는 작업은 다음과 같다.

- decision record를 실제 프로젝트 절차에 맞게 작성하는 흐름 보강
- `rollback` 명령의 안전한 실사용 검증
- `render`와 `pipeline`의 상태 표현을 더 일관되게 정리
- 외부 모델이 응답하지 않을 때의 UX 개선
- generated project 쪽 문서와 scorecard 설명의 정합성 유지

## 5. 작업 원칙

- 생성기 파일은 가능한 600라인 이하로 유지한다.
- 런타임 코드 문자열은 `templates/runtime/`로 분리한다.
- 모델 호출은 역할별로 분리하고, coder/reviewer는 decision gate를 통과해야 한다.
- 검증은 가능한 한 실제 생성 프로젝트에서 수행한다.

## 6. 한 줄 요약

현재 목표는 하니스 생성기와 생성 프로젝트 런타임을 분리된 구조로 유지하면서,
검색 증거, 의사결정, 검증, 로그, 스냅샷, 아카이브까지 연결된 실행 흐름을 완성하는 것이다.
