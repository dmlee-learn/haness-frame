# haness-frame 개발 요약

## 목표
하네스 프로젝트를 작은 소스 파일들로 분리된 상태로 유지하고, 생성되는 런타임은 `templates/runtime/`에 두며, 생성기 자체는 600라인 목표를 유지합니다.

## 현재 구현
- 프로젝트 생성은 `src/haness_frame_app/project_docs.py`가 담당합니다.
- 런타임 동작은 `src/haness_frame_app/templates/runtime/` 아래의 작은 템플릿 모듈들로 분리되어 있습니다.
- search evidence 수집이 구현되어 있습니다.
- coder와 reviewer 역할에 대한 decision gate 강제가 구현되어 있습니다.
- 역할 순서와 pipeline 실행이 구현되어 있습니다.
- snapshot과 rollback 지원이 구현되어 있습니다.
- archive 생성이 구현되어 있습니다.
- decision record 초안 생성이 구현되어 있습니다.
- 레거시 `haness_frame_back.py` 진입점은 얇은 호환 래퍼로 바뀌었습니다.
- evidence가 쌓인 뒤 gate가 막히면 `python app.py decision-draft`를 바로 안내하도록 상태 흐름이 바뀌었습니다.
- search evidence가 seeded 되었고 decision draft를 다시 만들면 gate가 열리도록 되어 있습니다.
- search plan에서 재사용 가능한 evidence 초안을 만들 수 있습니다.
- evidence 초안을 구조화된 evidence record로 다시 적재할 수 있습니다.
- search plan에서 evidence gap 보고서를 만들 수 있습니다.
- 기존 생성 프로젝트를 현재 런타임 템플릿과 동기화할 수 있습니다.
- `python app.py summary`로 status, evidence, gap을 개수 기반으로 빠르게 볼 수 있습니다.
- 테스트 흐름은 `localdoc/testing-process.en.md`와 `localdoc/testing-process.ko.md`에 정리되어 있습니다.
- 검증은 compileall, manifest 검증, decision gate 평가로 구성됩니다.

## 로컬 검증 완료
- `python -m compileall src`
- `python app.py manifest`
- `python app.py search-plan`
- `python app.py add-evidence ...`
- `python app.py snapshot --label ...`
- `python app.py rollback --name ...`
- `python app.py archive --label ...`
- `python app.py decision-template`
- `python app.py decision-draft`
- `python app.py evidence-draft`
- `python app.py evidence-commit`
- `python app.py evidence-gaps`
- `python app.py summary`
- `python app.py verify`

## 현재 집중점
- 소스 파일이 커지면 다시 분리합니다.
- 역할 오케스트레이션과 decision gate 강제를 안정적으로 유지합니다.
- 생성 프로젝트를 런타임 템플릿과 계속 맞춥니다.

## 남은 작업
- decision record 작업 흐름을 끝까지 더 쉽게 만듭니다.
- 현재 검증 상태가 더 분명하게 보이도록 status 출력을 다듬습니다.
- `localdoc/`를 현재 런타임 동작과 계속 맞춥니다.
