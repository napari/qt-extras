from __future__ import annotations

import weakref
from contextlib import contextmanager
from inspect import Parameter, Signature, ismethod, signature
from typing import TYPE_CHECKING, Any, Callable, Optional, Tuple, Union, overload

if TYPE_CHECKING:
    CallbackType = Callable[..., None]
    MethodRef = Tuple[weakref.ReferenceType[object], str]
    NormedCallback = Union[MethodRef, CallbackType]
    StoredSlot = Tuple[NormedCallback, int]


class Signal:

    # valid callback signatures for this signal.
    if TYPE_CHECKING:
        signatures: tuple[Signature, ...]
        _signal_instances: dict[Signal, weakref.WeakKeyDictionary[Any, SignalInstance]]

    _current_emitter: Optional[SignalInstance] = None

    def __init__(self, *types: Any, name: Optional[str] = None) -> None:
        self._signal_instances = {}
        self._name = None

        if not types:
            # single signature, no parameters
            self.signatures = (Signature(),)
        elif not isinstance(types[0], (list, tuple, Signature)):
            # single signature, with parameters
            self.signatures = (Signal._build_signature(*types),)
        else:
            # multiple signatures
            _signatures: list[Signature] = []
            for t in types:
                if isinstance(t, Signature):
                    _signatures.append(t)
                elif isinstance(t, (list, tuple)):
                    _signatures.append(Signal._build_signature(*t))
                else:
                    raise TypeError(
                        "each signature in a multi-signature sequence must be "
                        "experessed as a Signature, list, or tuple"
                    )
            self.signatures = tuple(_signatures)

    def __set_name__(self, owner: type, name):
        if self._name is None:
            self._name = name

    @staticmethod
    def _build_signature(*types: type) -> Signature:
        params = [
            Parameter(name=f"p{i}", kind=Parameter.POSITIONAL_ONLY, annotation=t)
            for i, t in enumerate(types)
        ]
        return Signature(params)

    def __getattr__(self, name):
        if name == "connect":
            name = self.__class__.__name__
            raise AttributeError(
                f"{name!r} object has no attribute 'connect'. You can connect to the "
                "signal on the *instance* of a class with a Signal() class attribute. "
                "Or create a signal instance directly with SignalInstance."
            )
        return self.__getattribute__(name)

    @overload
    def __get__(self, instance: None, owner: Optional[type] = None) -> Signal:
        ...

    @overload
    def __get__(self, instance: Any, owner: Optional[type] = None) -> SignalInstance:
        ...

    def __get__(
        self, instance: Any, owner: type = None
    ) -> Union[Signal, SignalInstance]:
        # if instance is not None, we're being accessed on an instance of `owner`
        # otherwise we're being accessed on the `owner` itself
        if instance is None:
            return self
        d = self._signal_instances.setdefault(self, weakref.WeakKeyDictionary())
        return d.setdefault(
            instance, SignalInstance(self.signatures, instance, name=self._name)
        )

    @classmethod
    @contextmanager
    def _emitting(cls, emitter: SignalInstance):
        """Context that sets the sender on a receiver object while emitting a signal."""
        previous, cls._current_emitter = cls._current_emitter, emitter
        try:
            yield
        finally:
            cls._current_emitter = previous

    @classmethod
    def current_emitter(cls) -> Optional[SignalInstance]:
        return cls._current_emitter

    @classmethod
    def sender(cls) -> Any:
        return getattr(cls._current_emitter, "instance", None)


class SignalInstance:
    def __init__(
        self,
        signatures: tuple[Signature, ...] = (Signature(),),
        instance: Any = None,
        name: Optional[str] = None,
    ) -> None:
        self.signatures = signatures
        self._instance: Any = instance
        self._name = name
        self._slots: list[StoredSlot] = []
        self._is_blocked: bool = False

    @property
    def instance(self) -> Any:
        return self._instance

    @property
    def name(self) -> Any:
        return self._name

    def __repr__(self) -> str:
        name = f"{self.name!r} " if self.name else ""
        return f"<{type(self).__name__} {name}on {self.instance!r}>"

    def __getitem__(self, key: object) -> SignalInstance:
        # used to return a version of self that accepts a specific signature
        pass

    def connect(
        self, slot: CallbackType, check_types=False, unique: Union[bool, str] = False
    ) -> None:
        """Connect a callback ("slot") to this signal.

        `slot` is compatible if:
            - it has equal or less required positional arguments
            - it has no required keyword arguments
            - if `check_types` is True, all provided types must match

        Parameters
        ----------
        slot : Callable
            A callable to connect to this signal.
        check_types : bool, optional
            If `True`, An additional check will be performed to make sure that types
            declared in the slot signature are compatible with at least one of the
            signatures provided by this slot, by default `False`.
        unique : bool or str, optional
            If `True`, returns without connecting if the slot has already been
            connected.  If the literal string "raise" is passed to `unique`, then a
            `ValueError` will be raised if the slot is already connected.
            By default `False`.

        Raises
        ------
        TypeError
            If a non-callable object is provided.
        ValueError
            If the provided slot fails validation, either due to mismatched positional
            argument requirements, or failed type checking.
        ValueError
            If `unique` is `True` and `slot` has already been connected.
        """
        if not callable(slot):
            raise TypeError(f"Cannot connect to non-callable object: {slot}")

        if unique and (slot in self):
            if unique == "raise":
                raise ValueError(
                    "Slot already connect. Use `connect(..., unique=False)` "
                    "to allow duplicate connections"
                )
            return

        # make sure we have a matching signature
        errors = []
        slot_sig = signature(slot)
        for spec in sorted(
            self.signatures, key=lambda x: len(x.parameters), reverse=True
        ):
            try:
                # get the maximum number of arguments that we can pass to the slot
                minargs, maxargs = _acceptable_posarg_range(slot_sig)
                n_spec_params = len(spec.parameters)

                if minargs > n_spec_params:
                    raise ValueError(
                        f"Slot requires at least {minargs} positional "
                        f"arguments, but spec only provides {n_spec_params}"
                    )

                if check_types and not _parameter_types_match(slot, spec, slot_sig):
                    raise ValueError(
                        f"Slot types {slot_sig} do not match types in {spec}"
                    )

                break  # if we made it here, we're good
            except ValueError as e:
                errors.append(e)
                continue
        else:
            name = getattr(slot, "__name__", str(slot))
            accepted = ",".join(str(x) for x in self.signatures)
            msg = f"Cannot connect slot {name!r} with signature: {signature(slot)}:"
            for err in errors:
                msg += f"\n - {err}"
            msg += f"\n\nAccepted signatures: {accepted}"
            raise ValueError(msg)

        # TODO: if unique is True, don't connect if it already exists
        self._slots.append((self._normalize_slot(slot), maxargs))

    def _normalize_slot(self, slot: NormedCallback) -> NormedCallback:
        if ismethod(slot):
            return (weakref.ref(slot.__self__), slot.__name__)  # type: ignore
        if isinstance(slot, tuple) and not isinstance(slot[0], weakref.ref):
            s0, s1, *_ = slot
            return (weakref.ref(s0), s1)
        return slot

    def _slot_index(self, slot) -> int:
        normed = self._normalize_slot(slot)
        for i, (s, m) in enumerate(self._slots):
            if s == normed:
                return i
        return -1

    def disconnect(
        self, slot: Optional[NormedCallback] = None, missing_ok=True
    ) -> None:
        if slot is None:
            # NOTE: clearing an empty list is actually a RuntimeError in Qt
            self._slots.clear()
            return

        # Qt behavior:
        # if the same object is connected multiple times,
        # this only removes the first one it finds...
        # Or raises a ValueError if not in the list
        idx = self._slot_index(slot)
        if idx >= 0:
            self._slots.pop(idx)
        elif not missing_ok:
            raise ValueError(f"slot is not connected: {slot}")

    def __contains__(self, slot) -> bool:
        return self._slot_index(slot) >= 0

    def __len__(self) -> int:
        return len(self._slots)

    def emit(self, *args: Any) -> None:
        """Emit this signal with arguments `args`."""
        if self._is_blocked:
            return

        # TODO: add signature checking on emit?  Qt has it...

        rem: list[NormedCallback] = []

        # allow receiver to query sender with Signal.current_emitter()
        with Signal._emitting(self):
            for (slot, max_args) in self._slots:
                if isinstance(slot, tuple):
                    _ref, method_name = slot
                    obj = _ref()
                    if obj is None:
                        rem.append(slot)  # add dead weakref
                        continue
                    cb = getattr(obj, method_name, None)
                    if cb is None:  # pragma: no cover
                        rem.append(slot)  # object has changed?
                        continue
                else:
                    cb = slot

                # TODO: add better exception handling
                cb(*args[:max_args])

        for slot in rem:
            self.disconnect(slot)

    def block(self, should_block: bool = True):
        """Sets blocking of the signal"""
        self._is_blocked = bool(should_block)

    def blocked(self):
        return SignalBlocker(self)


class SignalBlocker:
    """Context manager that blocks emission from `target`."""

    def __init__(self, target: SignalInstance):
        self.target = target

    def __enter__(self):
        self.target.block(True)
        return self

    def __exit__(self, *args):
        self.target.block(False)


# def f(a, /, b, c=None, *d, f=None, **g): print(locals())
#
# a: kind=POSITIONAL_ONLY,       default=Parameter.empty    # 1 required posarg
# b: kind=POSITIONAL_OR_KEYWORD, default=Parameter.empty    # 1 requires posarg
# c: kind=POSITIONAL_OR_KEYWORD, default=None               # 1 optional posarg
# d: kind=VAR_POSITIONAL,        default=Parameter.empty    # N optional posargs
# e: kind=KEYWORD_ONLY,          default=Parameter.empty    # 1 REQUIRED kwarg
# f: kind=KEYWORD_ONLY,          default=None               # 1 optional kwarg
# g: kind=VAR_KEYWORD,           default=Parameter.empty    # N optional kwargs


def _acceptable_posarg_range(
    sig: Signature, forbid_required_kwarg=True
) -> tuple[int, int]:
    """Returns tuple of (min, max) accepted positional arguments.

    Parameters
    ----------
    sig : Signature
        Signature object to evaluate
    no_required_kwarg : bool, optional
        Whether to allow required KEYWORD_ONLY parameters.

    Returns
    -------
    arg_range : Tuple[int, int]
        minimum, maximum number of acceptable positional arguments

    Raises
    ------
    ValueError
        If the signature has a required keyword_only parameter and `no_required_kwarg`
        is `True`.
    """
    required = 0
    optional = 0
    for param in sig.parameters.values():
        if param.kind in {Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD}:
            if param.default is Parameter.empty:
                required += 1
            else:
                optional += 1
        elif param.kind is Parameter.VAR_POSITIONAL:
            optional += 10 ** 10  # could use math.inf, but need an int for indexing.
        elif (
            param.kind is Parameter.KEYWORD_ONLY
            and param.default is Parameter.empty
            and forbid_required_kwarg
        ):
            raise ValueError("Required KEYWORD_ONLY parameters not allowed")
    return (required, required + optional)


def _parameter_types_match(
    function: Callable, spec: Signature, func_sig: Optional[Signature] = None
) -> bool:
    """Return True if types in `function` signature match `spec`."""
    fsig = func_sig or signature(function)

    func_hints = None
    for f_param, spec_param in zip(fsig.parameters.values(), spec.parameters.values()):
        f_anno = f_param.annotation
        if f_anno is fsig.empty:
            # if function parameter is not type annotated, allow it.
            continue

        if isinstance(f_anno, str):
            if func_hints is None:
                from typing_extensions import get_type_hints

                func_hints = get_type_hints(function)
            f_anno = func_hints.get(f_param.name)

        if not _is_subclass(f_anno, spec_param.annotation):
            return False
    return True


def _is_subclass(left: Any, right: type) -> bool:
    from inspect import isclass

    from typing_extensions import get_args, get_origin

    if not isclass(left):
        # look for Union
        origin = get_origin(left)
        if origin is Union:
            return any(issubclass(i, right) for i in get_args(left))
    return issubclass(left, right)
