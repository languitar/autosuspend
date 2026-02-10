# [10.0.0](https://github.com/languitar/autosuspend/compare/v9.0.1...v10.0.0) (2026-02-10)


* feat!: replace presuspend systemd unit with dbus integration ([5c2a080](https://github.com/languitar/autosuspend/commit/5c2a08049248c20dd1e4323feb12d11f82c6f130))


### BREAKING CHANGES

* dbus and pygobject are now a mandatory dependencies

## [9.0.1](https://github.com/languitar/autosuspend/compare/v9.0.0...v9.0.1) (2026-01-19)


### Bug Fixes

* support modern psutil versions ([f5e867f](https://github.com/languitar/autosuspend/commit/f5e867f966826ea976bf38c2572de0366167cdf3))

# [9.0.0](https://github.com/languitar/autosuspend/compare/v8.0.0...v9.0.0) (2025-08-03)


* build!: drop Python 3.10 support ([fa4b20c](https://github.com/languitar/autosuspend/commit/fa4b20c50ce5bcfd26ced5c460868fe0bd41f219))


### BREAKING CHANGES

* official support for Python 3.10 has been dropped

# [8.0.0](https://github.com/languitar/autosuspend/compare/v7.2.0...v8.0.0) (2025-06-21)


### Code Refactoring

* **deps:** remove pytz, require tzdata ([af7ea3a](https://github.com/languitar/autosuspend/commit/af7ea3a400425933fd44ec691b9b7f812055fd71))


### BREAKING CHANGES

* **deps:** new optional dependency tzdata when doing log parsing

# [7.2.0](https://github.com/languitar/autosuspend/compare/v7.1.0...v7.2.0) (2025-02-23)


### Features

* **systemd:** automatically enable/disable suspend hook ([772797a](https://github.com/languitar/autosuspend/commit/772797a8e4d9b3db7f609d20e73a0e66805ba2f1)), closes [#625](https://github.com/languitar/autosuspend/issues/625)

# [7.1.0](https://github.com/languitar/autosuspend/compare/v7.0.3...v7.1.0) (2025-01-12)


### Features

* official Python 3.13 support ([a8ea72d](https://github.com/languitar/autosuspend/commit/a8ea72d414621a13ff7705330bd731ffe94eeef8))

## [7.0.3](https://github.com/languitar/autosuspend/compare/v7.0.2...v7.0.3) (2024-11-19)


### Bug Fixes

* treat temporary failures as activity ([8c96853](https://github.com/languitar/autosuspend/commit/8c968530f011dad814df8c55794b058f3c751e8d)), closes [#589](https://github.com/languitar/autosuspend/issues/589)

## [7.0.2](https://github.com/languitar/autosuspend/compare/v7.0.1...v7.0.2) (2024-10-13)


### Bug Fixes

* **icalendar:** support icalendar v6 ([49bc89f](https://github.com/languitar/autosuspend/commit/49bc89fb2461758dd4d4f07016e88c8458192161))

## [7.0.1](https://github.com/languitar/autosuspend/compare/v7.0.0...v7.0.1) (2024-09-22)


### Bug Fixes

* **kodi-idle-time:** Send proper request ([8bb6dad](https://github.com/languitar/autosuspend/commit/8bb6dad7f325024d011008fc1f0e3d52a0b9f222))

# [7.0.0](https://github.com/languitar/autosuspend/compare/v6.1.1...v7.0.0) (2024-04-25)


* build!: drop Python 3.9 support ([3c4ae32](https://github.com/languitar/autosuspend/commit/3c4ae32c8e52f022f41e94c3a49dd89b9d02dcf2))


### Features

* officially support Python 3.12 ([de2f180](https://github.com/languitar/autosuspend/commit/de2f18010d166eb86fe15665aa7769f2105b02aa))


### BREAKING CHANGES

* Python 3.9 is not supported officially anymore. Python
    3.10 is the supported minimum version.

## [6.1.1](https://github.com/languitar/autosuspend/compare/v6.1.0...v6.1.1) (2024-02-12)


### Bug Fixes

* **docs:** add missing docs for new version subcommand ([fb248f7](https://github.com/languitar/autosuspend/commit/fb248f7a5706f81c20f7e88907e22cbd5c895cbb))

# [6.1.0](https://github.com/languitar/autosuspend/compare/v6.0.0...v6.1.0) (2024-02-11)


### Features

* **cli:** provide a version subcommand ([d51d836](https://github.com/languitar/autosuspend/commit/d51d836564a53b0dd5017fcd801e43b117542ebc)), closes [#482](https://github.com/languitar/autosuspend/issues/482)

# [6.0.0](https://github.com/languitar/autosuspend/compare/v5.0.0...v6.0.0) (2023-09-18)


* build!: modernize supported Python version ([31c8ccc](https://github.com/languitar/autosuspend/commit/31c8cccb503218691ffb045142b1297133ce5340))


### BREAKING CHANGES

* Python 3.8 has been deprecated and is not officially
  supported anymore.

# [5.0.0](https://github.com/languitar/autosuspend/compare/v4.3.3...v5.0.0) (2023-08-13)


* feat(logind)!: configure which session classes to process ([986e558](https://github.com/languitar/autosuspend/commit/986e558c2913bf30ebbab87025fe9722d5997aa7)), closes [#366](https://github.com/languitar/autosuspend/issues/366)


### BREAKING CHANGES

* LogindSessionIdle now only processes sessions of type
    "user" by default. Use the new configuration option classes to also
    include other types in case you need to include them in the checks.

## [4.3.3](https://github.com/languitar/autosuspend/compare/v4.3.2...v4.3.3) (2023-08-10)


### Bug Fixes

* **systemd:** handle timers without next execution time ([9fb83ea](https://github.com/languitar/autosuspend/commit/9fb83eac7d6cbe981e2ebfc1ec3c3b54fca19804)), closes [#403](https://github.com/languitar/autosuspend/issues/403)

## [4.3.2](https://github.com/languitar/autosuspend/compare/v4.3.1...v4.3.2) (2023-06-05)


### Bug Fixes

* release for sphinx 7 support ([569dfa5](https://github.com/languitar/autosuspend/commit/569dfa5954617929ae11529ece84f32810e10bee))

## [4.3.1](https://github.com/languitar/autosuspend/compare/v4.3.0...v4.3.1) (2023-05-16)


### Bug Fixes

* **ical:** support all versions of tzlocal ([9eb0b95](https://github.com/languitar/autosuspend/commit/9eb0b9549e11b612d47d007777cb83eac4c53f31))

# [4.3.0](https://github.com/languitar/autosuspend/compare/v4.2.0...v4.3.0) (2022-12-08)


### Features

* add seconds since the system became idle to logs ([cba13db](https://github.com/languitar/autosuspend/commit/cba13db8c50a5fbab05447c3f6ce74cf85898100)), closes [#281](https://github.com/languitar/autosuspend/issues/281)

# [4.2.0](https://github.com/languitar/autosuspend/compare/v4.1.1...v4.2.0) (2022-07-24)


### Features

* **wakeup:** add a systemd timer wakeup check ([7c687a2](https://github.com/languitar/autosuspend/commit/7c687a23f705d46c65ef400332483a32ff6eaa79))

## [4.1.1](https://github.com/languitar/autosuspend/compare/v4.1.0...v4.1.1) (2022-03-10)


### Bug Fixes

* allow tzlocal version >= 4 ([58e8634](https://github.com/languitar/autosuspend/commit/58e8634347cc5bf25cbfbfccfe874d05420bb995))

# [4.1.0](https://github.com/languitar/autosuspend/compare/v4.0.1...v4.1.0) (2021-12-28)


### Features

* add official Python 3.10 support ([e5b2e49](https://github.com/languitar/autosuspend/commit/e5b2e494986d13ac29a06cfac0c5a6601c372671))

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
