## [4.0.1](https://github.com/languitar/autosuspend/compare/v4.0.0...v4.0.1) (2021-10-26)


### Bug Fixes

* **activity:** detect ipv4 mapped ipv6 connections ([a81e456](https://github.com/languitar/autosuspend/commit/a81e456aa89737a0a2f03ec5af5ffaf2e7738073)), closes [#116](https://github.com/languitar/autosuspend/issues/116)

# [4.0.0](https://github.com/languitar/autosuspend/compare/v3.1.4...v4.0.0) (2021-09-20)


* chore(build)!: drop tests on Python 3.7 ([06dce98](https://github.com/languitar/autosuspend/commit/06dce98882d5c8fa4d5e90623660c43d006eefa0))


### BREAKING CHANGES

* Python 3.7 isn't used anymore on any LTS Ubuntu or
    Debian release. No need to support such an old version anymore.

## [3.1.4](https://github.com/languitar/autosuspend/compare/v3.1.3...v3.1.4) (2021-09-20)


### Bug Fixes

* **ical:** limit tzlocal to version <3 ([623cd37](https://github.com/languitar/autosuspend/commit/623cd371df03a6fe3305eca4cf9e57c4d76b5c8a))

## [3.1.3](https://github.com/languitar/autosuspend/compare/v3.1.2...v3.1.3) (2021-03-29)

## [3.1.2](https://github.com/languitar/autosuspend/compare/v3.1.1...v3.1.2) (2021-03-29)

## [3.1.1](https://github.com/languitar/autosuspend/compare/v3.1.0...v3.1.1) (2021-03-28)


### Bug Fixes

* fix automatic version file generation ([aeb601d](https://github.com/languitar/autosuspend/commit/aeb601d523791780e5da592476b365bbc4b3f4c5))

## [3.1.0](https://github.com/languitar/autosuspend/compare/v3.0.1...v3.1.0) (2021-03-28)


### Features

* add semantic-release for automatic releases ([ac5ec86](https://github.com/languitar/autosuspend/commit/ac5ec8617681b537714f8eb8fef4ce0872989f2a))


### Bug Fixes

* use jsonpath ext to support filter expressions ([24d1be1](https://github.com/languitar/autosuspend/commit/24d1be1fcbd59d8e29a1bbfdc162e253e2f239c4)), closes [#102](https://github.com/languitar/autosuspend/issues/102)
