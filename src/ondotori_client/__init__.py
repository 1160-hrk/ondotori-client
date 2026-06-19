from __future__ import annotations

import logging

from .client import DateTimeInput, OndotoriClient
from .config import (
    BaseConfig,
    ClientConfig,
    Credentials,
    DeviceType,
    RemoteConfig,
    validate_device_type,
)
from .exceptions import (
    APIError,
    AuthenticationError,
    ConfigurationError,
    OndotoriError,
    RateLimitError,
    RequestValidationError,
    ResponseFormatError,
    TransportError,
)
from .models import (
    ChannelReading,
    MeasurementRecord,
    ResolvedRemote,
    TemperatureHumidityReading,
    TimeRange,
)
from .parsers import (
    parse_current,
    parse_current_record,
    parse_current_records,
    parse_current_temperature_humidity,
    parse_data,
    parse_data_records,
    parse_temperature_humidity_data,
    to_temperature_humidity,
)
from .transport import HTTPTransport, RetryPolicy, Timeout

__version__ = "0.4.0"

logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "APIError",
    "AuthenticationError",
    "BaseConfig",
    "ChannelReading",
    "ClientConfig",
    "ConfigurationError",
    "Credentials",
    "DateTimeInput",
    "DeviceType",
    "HTTPTransport",
    "MeasurementRecord",
    "OndotoriClient",
    "OndotoriError",
    "RateLimitError",
    "RemoteConfig",
    "RequestValidationError",
    "ResolvedRemote",
    "ResponseFormatError",
    "RetryPolicy",
    "TemperatureHumidityReading",
    "TimeRange",
    "Timeout",
    "TransportError",
    "__version__",
    "parse_current",
    "parse_current_record",
    "parse_current_records",
    "parse_current_temperature_humidity",
    "parse_data",
    "parse_data_records",
    "parse_temperature_humidity_data",
    "to_temperature_humidity",
    "validate_device_type",
]
