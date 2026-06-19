# 保存先:
# src/ondotori_client/config.py
#
# Ondotori WebStorage API の設定モデル，JSON 読み込み，
# 明示的な設定保存を担当するモジュールです．

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, TypeAlias, cast

from .exceptions import ConfigurationError


DeviceType: TypeAlias = Literal["default", "rtr500"]

_SUPPORTED_DEVICE_TYPES: frozenset[str] = frozenset(
    {
        "default",
        "rtr500",
    }
)


def validate_device_type(value: str) -> DeviceType:
    """
    デバイスタイプを検証する．

    Args:
        value:
            検証する文字列．

    Returns:
        "default" または "rtr500"．

    Raises:
        ConfigurationError:
            未対応のデバイスタイプが指定された場合．
    """
    if value not in _SUPPORTED_DEVICE_TYPES:
        supported = ", ".join(sorted(_SUPPORTED_DEVICE_TYPES))
        raise ConfigurationError(
            f"未対応の device_type です: {value!r}．"
            f"使用可能な値: {supported}"
        )

    return cast(DeviceType, value)


def _require_mapping(
    value: object,
    *,
    field_name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigurationError(
            f"{field_name!r} はオブジェクト形式で指定してください"
        )

    return cast(Mapping[str, Any], value)


def _require_nonempty_string(
    value: object,
    *,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(
            f"{field_name!r} には空でない文字列を指定してください"
        )

    return value.strip()


def _optional_nonempty_string(
    value: object,
    *,
    field_name: str,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str):
        raise ConfigurationError(
            f"{field_name!r} には文字列または null を指定してください"
        )

    normalized = value.strip()
    return normalized or None


@dataclass(frozen=True, slots=True)
class Credentials:
    """
    Ondotori WebStorage API の認証情報．

    Attributes:
        api_key:
            WebStorage API キー．
        login_id:
            WebStorage のログイン ID．
        login_pass:
            WebStorage のログインパスワード．
    """

    api_key: str
    login_id: str
    login_pass: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "api_key",
            _require_nonempty_string(
                self.api_key,
                field_name="api_key",
            ),
        )
        object.__setattr__(
            self,
            "login_id",
            _require_nonempty_string(
                self.login_id,
                field_name="login_id",
            ),
        )
        object.__setattr__(
            self,
            "login_pass",
            _require_nonempty_string(
                self.login_pass,
                field_name="login_pass",
            ),
        )

    def to_api_payload(self) -> dict[str, str]:
        """
        WebStorage API が要求するキー名へ変換する．
        """
        return {
            "api-key": self.api_key,
            "login-id": self.login_id,
            "login-pass": self.login_pass,
        }


@dataclass(frozen=True, slots=True)
class BaseConfig:
    """
    RTR500B 親機の設定．

    Attributes:
        serial:
            親機のシリアル番号．
    """

    serial: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "serial",
            _require_nonempty_string(
                self.serial,
                field_name="base.serial",
            ),
        )


@dataclass(frozen=True, slots=True)
class RemoteConfig:
    """
    子機または通常機器の設定．

    Attributes:
        serial:
            機器のシリアル番号．
        device_type:
            "default" または "rtr500"．
        base:
            RTR500B 親機の設定名．
            省略時は ClientConfig.default_rtr500_base を使用する．
    """

    serial: str
    device_type: DeviceType = "default"
    base: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "serial",
            _require_nonempty_string(
                self.serial,
                field_name="remote.serial",
            ),
        )
        object.__setattr__(
            self,
            "device_type",
            validate_device_type(self.device_type),
        )
        object.__setattr__(
            self,
            "base",
            _optional_nonempty_string(
                self.base,
                field_name="remote.base",
            ),
        )


@dataclass(frozen=True, slots=True)
class ClientConfig:
    """
    OndotoriClient 全体の設定．

    Attributes:
        credentials:
            API の認証情報．
        bases:
            RTR500B 親機名から設定へのマッピング．
        remotes:
            利用者が付けた機器名から設定へのマッピング．
        default_rtr500_base:
            RTR500B 機器で親機を省略した場合に使用する親機名．
    """

    credentials: Credentials
    bases: dict[str, BaseConfig] = field(default_factory=dict)
    remotes: dict[str, RemoteConfig] = field(default_factory=dict)
    default_rtr500_base: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.credentials, Credentials):
            raise ConfigurationError(
                "credentials には Credentials インスタンスを指定してください"
            )

        normalized_bases: dict[str, BaseConfig] = {}
        for name, base in self.bases.items():
            normalized_name = _require_nonempty_string(
                name,
                field_name="bases のキー",
            )

            if not isinstance(base, BaseConfig):
                raise ConfigurationError(
                    f"bases[{normalized_name!r}] は "
                    "BaseConfig インスタンスである必要があります"
                )

            normalized_bases[normalized_name] = base

        normalized_remotes: dict[str, RemoteConfig] = {}
        for name, remote in self.remotes.items():
            normalized_name = _require_nonempty_string(
                name,
                field_name="remote_map のキー",
            )

            if not isinstance(remote, RemoteConfig):
                raise ConfigurationError(
                    f"remotes[{normalized_name!r}] は "
                    "RemoteConfig インスタンスである必要があります"
                )

            normalized_remotes[normalized_name] = remote

        normalized_default_base = _optional_nonempty_string(
            self.default_rtr500_base,
            field_name="default_rtr500_base",
        )

        object.__setattr__(self, "bases", normalized_bases)
        object.__setattr__(self, "remotes", normalized_remotes)
        object.__setattr__(
            self,
            "default_rtr500_base",
            normalized_default_base,
        )

        self._validate_references()

    def _validate_references(self) -> None:
        """
        親機名への参照整合性を検証する．
        """
        if (
            self.default_rtr500_base is not None
            and self.default_rtr500_base not in self.bases
        ):
            raise ConfigurationError(
                "default_rtr500_base が存在しない親機を参照しています: "
                f"{self.default_rtr500_base!r}"
            )

        for remote_name, remote in self.remotes.items():
            if remote.base is not None and remote.base not in self.bases:
                raise ConfigurationError(
                    f"remote_map[{remote_name!r}] が存在しない親機を"
                    f"参照しています: {remote.base!r}"
                )

            if remote.device_type != "rtr500":
                continue

            base_name = remote.base or self.default_rtr500_base

            if base_name is None:
                raise ConfigurationError(
                    f"RTR500 機器 {remote_name!r} に親機が設定されていません．"
                    "remote_map の base または default_rtr500_base を"
                    "設定してください"
                )

            if base_name not in self.bases:
                raise ConfigurationError(
                    f"RTR500 機器 {remote_name!r} が存在しない親機を"
                    f"参照しています: {base_name!r}"
                )

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
    ) -> ClientConfig:
        """
        JSON 相当の辞書から設定を生成する．

        Args:
            data:
                config.json を読み込んだ辞書．

        Returns:
            検証済みの ClientConfig．

        Raises:
            ConfigurationError:
                必須項目の欠落や型の不整合がある場合．
        """
        if not isinstance(data, Mapping):
            raise ConfigurationError(
                "設定全体はオブジェクト形式で指定してください"
            )

        try:
            api_key_raw = data["api_key"]
        except KeyError as exc:
            raise ConfigurationError(
                "設定に必須項目 'api_key' がありません"
            ) from exc

        try:
            login_id_raw = data["login_id"]
        except KeyError as exc:
            raise ConfigurationError(
                "設定に必須項目 'login_id' がありません"
            ) from exc

        try:
            login_pass_raw = data["login_pass"]
        except KeyError as exc:
            raise ConfigurationError(
                "設定に必須項目 'login_pass' がありません"
            ) from exc

        credentials = Credentials(
            api_key=_require_nonempty_string(
                api_key_raw,
                field_name="api_key",
            ),
            login_id=_require_nonempty_string(
                login_id_raw,
                field_name="login_id",
            ),
            login_pass=_require_nonempty_string(
                login_pass_raw,
                field_name="login_pass",
            ),
        )

        bases_raw = data.get("bases", {})
        if bases_raw is None:
            bases_raw = {}

        bases_mapping = _require_mapping(
            bases_raw,
            field_name="bases",
        )

        bases: dict[str, BaseConfig] = {}

        for base_name_raw, base_data_raw in bases_mapping.items():
            base_name = _require_nonempty_string(
                base_name_raw,
                field_name="bases のキー",
            )
            base_data = _require_mapping(
                base_data_raw,
                field_name=f"bases[{base_name!r}]",
            )

            if "serial" not in base_data:
                raise ConfigurationError(
                    f"bases[{base_name!r}] に必須項目 'serial' がありません"
                )

            bases[base_name] = BaseConfig(
                serial=_require_nonempty_string(
                    base_data["serial"],
                    field_name=f"bases[{base_name!r}].serial",
                )
            )

        remotes_raw = data.get("remote_map", {})
        if remotes_raw is None:
            remotes_raw = {}

        remotes_mapping = _require_mapping(
            remotes_raw,
            field_name="remote_map",
        )

        remotes: dict[str, RemoteConfig] = {}

        for remote_name_raw, remote_data_raw in remotes_mapping.items():
            remote_name = _require_nonempty_string(
                remote_name_raw,
                field_name="remote_map のキー",
            )
            remote_data = _require_mapping(
                remote_data_raw,
                field_name=f"remote_map[{remote_name!r}]",
            )

            if "serial" not in remote_data:
                raise ConfigurationError(
                    f"remote_map[{remote_name!r}] に"
                    "必須項目 'serial' がありません"
                )

            device_type_raw = remote_data.get("type", "default")
            device_type_string = _require_nonempty_string(
                device_type_raw,
                field_name=f"remote_map[{remote_name!r}].type",
            )

            remotes[remote_name] = RemoteConfig(
                serial=_require_nonempty_string(
                    remote_data["serial"],
                    field_name=f"remote_map[{remote_name!r}].serial",
                ),
                device_type=validate_device_type(device_type_string),
                base=_optional_nonempty_string(
                    remote_data.get("base"),
                    field_name=f"remote_map[{remote_name!r}].base",
                ),
            )

        default_base = _optional_nonempty_string(
            data.get("default_rtr500_base"),
            field_name="default_rtr500_base",
        )

        return cls(
            credentials=credentials,
            bases=bases,
            remotes=remotes,
            default_rtr500_base=default_base,
        )

    @classmethod
    def from_file(
        cls,
        path: str | os.PathLike[str],
    ) -> ClientConfig:
        """
        JSON 設定ファイルから設定を読み込む．

        Args:
            path:
                config.json のパス．

        Returns:
            検証済みの ClientConfig．

        Raises:
            ConfigurationError:
                ファイルを開けない，JSON が不正，または設定内容が不正な場合．
        """
        config_path = Path(path).expanduser()

        try:
            with config_path.open(
                mode="r",
                encoding="utf-8",
            ) as file:
                raw_data = json.load(file)
        except FileNotFoundError as exc:
            raise ConfigurationError(
                f"設定ファイルが見つかりません: {config_path}"
            ) from exc
        except PermissionError as exc:
            raise ConfigurationError(
                f"設定ファイルを読み込む権限がありません: {config_path}"
            ) from exc
        except OSError as exc:
            raise ConfigurationError(
                f"設定ファイルを読み込めませんでした: {config_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise ConfigurationError(
                f"設定ファイルの JSON が不正です: {config_path} "
                f"(line={exc.lineno}, column={exc.colno})"
            ) from exc

        if not isinstance(raw_data, Mapping):
            raise ConfigurationError(
                f"設定ファイルのルートはオブジェクトである必要があります: "
                f"{config_path}"
            )

        return cls.from_mapping(raw_data)

    @classmethod
    def from_credentials(
        cls,
        *,
        api_key: str,
        login_id: str,
        login_pass: str,
        base_serial: str | None = None,
    ) -> ClientConfig:
        """
        認証情報を直接指定して設定を生成する．

        base_serial を指定した場合は，内部的に "default" という名前の
        RTR500B 親機設定を作成する．

        Args:
            api_key:
                API キー．
            login_id:
                ログイン ID．
            login_pass:
                ログインパスワード．
            base_serial:
                任意の RTR500B 親機シリアル番号．

        Returns:
            ClientConfig．
        """
        credentials = Credentials(
            api_key=api_key,
            login_id=login_id,
            login_pass=login_pass,
        )

        if base_serial is None:
            return cls(credentials=credentials)

        return cls(
            credentials=credentials,
            bases={
                "default": BaseConfig(
                    serial=base_serial,
                )
            },
            default_rtr500_base="default",
        )

    def to_mapping(self) -> dict[str, Any]:
        """
        config.json と同じ構造の辞書へ変換する．

        注意:
            戻り値にはログインパスワードを含む認証情報が格納される．
        """
        bases_output = {
            name: {
                "serial": base.serial,
            }
            for name, base in self.bases.items()
        }

        remote_map_output: dict[str, dict[str, str]] = {}

        for name, remote in self.remotes.items():
            remote_output = {
                "serial": remote.serial,
                "type": remote.device_type,
            }

            if remote.base is not None:
                remote_output["base"] = remote.base

            remote_map_output[name] = remote_output

        return {
            "api_key": self.credentials.api_key,
            "login_id": self.credentials.login_id,
            "login_pass": self.credentials.login_pass,
            "default_rtr500_base": self.default_rtr500_base,
            "bases": bases_output,
            "remote_map": remote_map_output,
        }

    def save(
        self,
        path: str | os.PathLike[str],
        *,
        overwrite: bool = False,
    ) -> Path:
        """
        設定を JSON ファイルへ明示的に保存する．

        一時ファイルへ書き込んだ後，os.replace() で置き換える．
        Unix 系環境では可能な範囲でファイル権限を 0o600 に設定する．

        Args:
            path:
                保存先のパス．
            overwrite:
                True の場合のみ既存ファイルを上書きする．

        Returns:
            保存先の Path．

        Raises:
            ConfigurationError:
                保存先が既に存在する，または保存に失敗した場合．
        """
        output_path = Path(path).expanduser()

        if output_path.exists() and not overwrite:
            raise ConfigurationError(
                f"設定ファイルは既に存在します: {output_path}．"
                "上書きする場合は overwrite=True を指定してください"
            )

        try:
            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as exc:
            raise ConfigurationError(
                f"保存先ディレクトリを作成できませんでした: "
                f"{output_path.parent}"
            ) from exc

        temporary_path: Path | None = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=output_path.parent,
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)

                json.dump(
                    self.to_mapping(),
                    temporary_file,
                    ensure_ascii=False,
                    indent=2,
                )
                temporary_file.write("\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())

            try:
                os.chmod(temporary_path, 0o600)
            except OSError:
                # Windows など，Unix 形式の権限設定が完全には
                # 利用できない環境では保存処理を継続する．
                pass

            os.replace(
                temporary_path,
                output_path,
            )
            temporary_path = None

        except OSError as exc:
            raise ConfigurationError(
                f"設定ファイルを保存できませんでした: {output_path}"
            ) from exc
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

        return output_path


__all__ = [
    "DeviceType",
    "Credentials",
    "BaseConfig",
    "RemoteConfig",
    "ClientConfig",
    "validate_device_type",
]