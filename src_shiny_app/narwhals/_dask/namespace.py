from __future__ import annotations

from functools import reduce
from typing import TYPE_CHECKING
from typing import Any
from typing import Callable
from typing import Iterable
from typing import Literal
from typing import NoReturn
from typing import cast

from narwhals._dask.dataframe import DaskLazyFrame
from narwhals._dask.expr import DaskExpr
from narwhals._dask.selectors import DaskSelectorNamespace
from narwhals._dask.utils import name_preserving_div
from narwhals._dask.utils import name_preserving_sum
from narwhals._dask.utils import narwhals_to_native_dtype
from narwhals._dask.utils import validate_comparand
from narwhals._expression_parsing import combine_root_names
from narwhals._expression_parsing import parse_into_exprs
from narwhals._expression_parsing import reduce_output_names

if TYPE_CHECKING:
    import dask_expr

    from narwhals._dask.typing import IntoDaskExpr
    from narwhals.dtypes import DType
    from narwhals.utils import Version


class DaskNamespace:
    @property
    def selectors(self) -> DaskSelectorNamespace:
        return DaskSelectorNamespace(
            backend_version=self._backend_version, version=self._version
        )

    def __init__(self, *, backend_version: tuple[int, ...], version: Version) -> None:
        self._backend_version = backend_version
        self._version = version

    def all(self) -> DaskExpr:
        def func(df: DaskLazyFrame) -> list[dask_expr.Series]:
            return [df._native_frame[column_name] for column_name in df.columns]

        return DaskExpr(
            func,
            depth=0,
            function_name="all",
            root_names=None,
            output_names=None,
            returns_scalar=False,
            backend_version=self._backend_version,
            version=self._version,
        )

    def col(self, *column_names: str) -> DaskExpr:
        return DaskExpr.from_column_names(
            *column_names, backend_version=self._backend_version, version=self._version
        )

    def nth(self, *column_indices: int) -> DaskExpr:
        return DaskExpr.from_column_indices(
            *column_indices, backend_version=self._backend_version, version=self._version
        )

    def lit(self, value: Any, dtype: DType | None) -> DaskExpr:
        def convert_if_dtype(
            series: dask_expr.Series, dtype: DType | type[DType]
        ) -> dask_expr.Series:
            return (
                series.astype(narwhals_to_native_dtype(dtype, self._version))
                if dtype
                else series
            )

        return DaskExpr(
            lambda df: [
                df._native_frame.assign(literal=value)["literal"].pipe(
                    convert_if_dtype, dtype
                )
            ],
            depth=0,
            function_name="lit",
            root_names=None,
            output_names=["literal"],
            returns_scalar=False,
            backend_version=self._backend_version,
            version=self._version,
        )

    def min(self, *column_names: str) -> DaskExpr:
        return DaskExpr.from_column_names(
            *column_names, backend_version=self._backend_version, version=self._version
        ).min()

    def max(self, *column_names: str) -> DaskExpr:
        return DaskExpr.from_column_names(
            *column_names, backend_version=self._backend_version, version=self._version
        ).max()

    def mean(self, *column_names: str) -> DaskExpr:
        return DaskExpr.from_column_names(
            *column_names, backend_version=self._backend_version, version=self._version
        ).mean()

    def median(self, *column_names: str) -> DaskExpr:
        return DaskExpr.from_column_names(
            *column_names, backend_version=self._backend_version, version=self._version
        ).median()

    def sum(self, *column_names: str) -> DaskExpr:
        return DaskExpr.from_column_names(
            *column_names, backend_version=self._backend_version, version=self._version
        ).sum()

    def len(self) -> DaskExpr:
        import dask.dataframe as dd
        import pandas as pd

        def func(df: DaskLazyFrame) -> list[dask_expr.Series]:
            if not df.columns:
                return [
                    dd.from_pandas(
                        pd.Series([0], name="len"),
                        npartitions=df._native_frame.npartitions,
                    )
                ]
            return [df._native_frame[df.columns[0]].size.to_series().rename("len")]

        # coverage bug? this is definitely hit
        return DaskExpr(  # pragma: no cover
            func,
            depth=0,
            function_name="len",
            root_names=None,
            output_names=["len"],
            returns_scalar=True,
            backend_version=self._backend_version,
            version=self._version,
        )

    def all_horizontal(self, *exprs: IntoDaskExpr) -> DaskExpr:
        parsed_exprs = parse_into_exprs(*exprs, namespace=self)

        def func(df: DaskLazyFrame) -> list[dask_expr.Series]:
            series = [s for _expr in parsed_exprs for s in _expr._call(df)]
            return [reduce(lambda x, y: x & y, series).rename(series[0].name)]

        return DaskExpr(
            call=func,
            depth=max(x._depth for x in parsed_exprs) + 1,
            function_name="all_horizontal",
            root_names=combine_root_names(parsed_exprs),
            output_names=reduce_output_names(parsed_exprs),
            returns_scalar=False,
            backend_version=self._backend_version,
            version=self._version,
        )

    def any_horizontal(self, *exprs: IntoDaskExpr) -> DaskExpr:
        parsed_exprs = parse_into_exprs(*exprs, namespace=self)

        def func(df: DaskLazyFrame) -> list[dask_expr.Series]:
            series = [s for _expr in parsed_exprs for s in _expr._call(df)]
            return [reduce(lambda x, y: x | y, series).rename(series[0].name)]

        return DaskExpr(
            call=func,
            depth=max(x._depth for x in parsed_exprs) + 1,
            function_name="any_horizontal",
            root_names=combine_root_names(parsed_exprs),
            output_names=reduce_output_names(parsed_exprs),
            returns_scalar=False,
            backend_version=self._backend_version,
            version=self._version,
        )

    def sum_horizontal(self, *exprs: IntoDaskExpr) -> DaskExpr:
        parsed_exprs = parse_into_exprs(*exprs, namespace=self)

        def func(df: DaskLazyFrame) -> list[dask_expr.Series]:
            series = [s.fillna(0) for _expr in parsed_exprs for s in _expr._call(df)]
            return [reduce(lambda x, y: x + y, series).rename(series[0].name)]

        return DaskExpr(
            call=func,
            depth=max(x._depth for x in parsed_exprs) + 1,
            function_name="sum_horizontal",
            root_names=combine_root_names(parsed_exprs),
            output_names=reduce_output_names(parsed_exprs),
            returns_scalar=False,
            backend_version=self._backend_version,
            version=self._version,
        )

    def concat(
        self,
        items: Iterable[DaskLazyFrame],
        *,
        how: Literal["horizontal", "vertical", "diagonal"],
    ) -> DaskLazyFrame:
        import dask.dataframe as dd

        if len(list(items)) == 0:
            msg = "No items to concatenate"  # pragma: no cover
            raise AssertionError(msg)
        dfs = [i._native_frame for i in items]
        cols_0 = dfs[0].columns
        if how == "vertical":
            for i, df in enumerate(dfs[1:], start=1):
                cols_current = df.columns
                if not (
                    (len(cols_current) == len(cols_0)) and (cols_current == cols_0).all()
                ):
                    msg = (
                        "unable to vstack, column names don't match:\n"
                        f"   - dataframe 0: {cols_0.to_list()}\n"
                        f"   - dataframe {i}: {cols_current.to_list()}\n"
                    )
                    raise TypeError(msg)
            return DaskLazyFrame(
                dd.concat(dfs, axis=0, join="inner"),
                backend_version=self._backend_version,
                version=self._version,
            )
        if how == "horizontal":
            all_column_names: list[str] = [
                column for frame in dfs for column in frame.columns
            ]
            if len(all_column_names) != len(set(all_column_names)):  # pragma: no cover
                duplicates = [
                    i for i in all_column_names if all_column_names.count(i) > 1
                ]
                msg = (
                    f"Columns with name(s): {', '.join(duplicates)} "
                    "have more than one occurrence"
                )
                raise AssertionError(msg)
            return DaskLazyFrame(
                dd.concat(dfs, axis=1, join="outer"),
                backend_version=self._backend_version,
                version=self._version,
            )
        if how == "diagonal":
            return DaskLazyFrame(
                dd.concat(dfs, axis=0, join="outer"),
                backend_version=self._backend_version,
                version=self._version,
            )

        raise NotImplementedError

    def mean_horizontal(self, *exprs: IntoDaskExpr) -> DaskExpr:
        parsed_exprs = parse_into_exprs(*exprs, namespace=self)

        def func(df: DaskLazyFrame) -> list[dask_expr.Series]:
            series = (s.fillna(0) for _expr in parsed_exprs for s in _expr._call(df))
            non_na = (1 - s.isna() for _expr in parsed_exprs for s in _expr._call(df))
            return [
                name_preserving_div(
                    reduce(name_preserving_sum, series),
                    reduce(name_preserving_sum, non_na),
                )
            ]

        return DaskExpr(
            call=func,
            depth=max(x._depth for x in parsed_exprs) + 1,
            function_name="mean_horizontal",
            root_names=combine_root_names(parsed_exprs),
            output_names=reduce_output_names(parsed_exprs),
            returns_scalar=False,
            backend_version=self._backend_version,
            version=self._version,
        )

    def min_horizontal(self, *exprs: IntoDaskExpr) -> DaskExpr:
        import dask.dataframe as dd

        parsed_exprs = parse_into_exprs(*exprs, namespace=self)

        def func(df: DaskLazyFrame) -> list[dask_expr.Series]:
            series = [s for _expr in parsed_exprs for s in _expr._call(df)]

            return [dd.concat(series, axis=1).min(axis=1).rename(series[0].name)]

        return DaskExpr(
            call=func,
            depth=max(x._depth for x in parsed_exprs) + 1,
            function_name="min_horizontal",
            root_names=combine_root_names(parsed_exprs),
            output_names=reduce_output_names(parsed_exprs),
            returns_scalar=False,
            backend_version=self._backend_version,
            version=self._version,
        )

    def max_horizontal(self, *exprs: IntoDaskExpr) -> DaskExpr:
        import dask.dataframe as dd

        parsed_exprs = parse_into_exprs(*exprs, namespace=self)

        def func(df: DaskLazyFrame) -> list[dask_expr.Series]:
            series = [s for _expr in parsed_exprs for s in _expr._call(df)]

            return [dd.concat(series, axis=1).max(axis=1).rename(series[0].name)]

        return DaskExpr(
            call=func,
            depth=max(x._depth for x in parsed_exprs) + 1,
            function_name="max_horizontal",
            root_names=combine_root_names(parsed_exprs),
            output_names=reduce_output_names(parsed_exprs),
            returns_scalar=False,
            backend_version=self._backend_version,
            version=self._version,
        )

    def _create_expr_from_series(self, _: Any) -> NoReturn:
        msg = "`_create_expr_from_series` for DaskNamespace exists only for compatibility"
        raise NotImplementedError(msg)

    def _create_compliant_series(self, _: Any) -> NoReturn:
        msg = "`_create_compliant_series` for DaskNamespace exists only for compatibility"
        raise NotImplementedError(msg)

    def _create_series_from_scalar(
        self, value: Any, *, reference_series: DaskExpr
    ) -> NoReturn:
        msg = (
            "`_create_series_from_scalar` for DaskNamespace exists only for compatibility"
        )
        raise NotImplementedError(msg)

    def _create_expr_from_callable(  # pragma: no cover
        self,
        func: Callable[[DaskLazyFrame], list[DaskExpr]],
        *,
        depth: int,
        function_name: str,
        root_names: list[str] | None,
        output_names: list[str] | None,
    ) -> DaskExpr:
        msg = (
            "`_create_expr_from_callable` for DaskNamespace exists only for compatibility"
        )
        raise NotImplementedError(msg)

    def when(
        self,
        *predicates: IntoDaskExpr,
    ) -> DaskWhen:
        plx = self.__class__(backend_version=self._backend_version, version=self._version)
        if predicates:
            condition = plx.all_horizontal(*predicates)
        else:
            msg = "at least one predicate needs to be provided"
            raise TypeError(msg)

        return DaskWhen(
            condition, self._backend_version, returns_scalar=False, version=self._version
        )

    def concat_str(
        self,
        exprs: Iterable[IntoDaskExpr],
        *more_exprs: IntoDaskExpr,
        separator: str = "",
        ignore_nulls: bool = False,
    ) -> DaskExpr:
        parsed_exprs: list[DaskExpr] = [
            *parse_into_exprs(*exprs, namespace=self),
            *parse_into_exprs(*more_exprs, namespace=self),
        ]

        def func(df: DaskLazyFrame) -> list[dask_expr.Series]:
            series = (s.astype(str) for _expr in parsed_exprs for s in _expr._call(df))
            null_mask = [s for _expr in parsed_exprs for s in _expr.is_null()._call(df)]

            if not ignore_nulls:
                null_mask_result = reduce(lambda x, y: x | y, null_mask)
                result = reduce(lambda x, y: x + separator + y, series).where(
                    ~null_mask_result, None
                )
            else:
                init_value, *values = [
                    s.where(~nm, "") for s, nm in zip(series, null_mask)
                ]

                separators = (
                    nm.map({True: "", False: separator}, meta=str)
                    for nm in null_mask[:-1]
                )
                result = reduce(
                    lambda x, y: x + y,
                    (s + v for s, v in zip(separators, values)),
                    init_value,
                )

            return [result]

        return DaskExpr(
            call=func,
            depth=max(x._depth for x in parsed_exprs) + 1,
            function_name="concat_str",
            root_names=combine_root_names(parsed_exprs),
            output_names=reduce_output_names(parsed_exprs),
            returns_scalar=False,
            backend_version=self._backend_version,
            version=self._version,
        )


class DaskWhen:
    def __init__(
        self,
        condition: DaskExpr,
        backend_version: tuple[int, ...],
        then_value: Any = None,
        otherwise_value: Any = None,
        *,
        returns_scalar: bool,
        version: Version,
    ) -> None:
        self._backend_version = backend_version
        self._condition = condition
        self._then_value = then_value
        self._otherwise_value = otherwise_value
        self._returns_scalar = returns_scalar
        self._version = version

    def __call__(self, df: DaskLazyFrame) -> list[dask_expr.Series]:
        from narwhals._dask.namespace import DaskNamespace
        from narwhals._expression_parsing import parse_into_expr

        plx = DaskNamespace(backend_version=self._backend_version, version=self._version)

        condition = parse_into_expr(self._condition, namespace=plx)._call(df)[0]
        condition = cast("dask_expr.Series", condition)
        try:
            value_series = parse_into_expr(self._then_value, namespace=plx)._call(df)[0]
        except TypeError:
            # `self._otherwise_value` is a scalar and can't be converted to an expression
            _df = condition.to_frame("a")
            _df["tmp"] = self._then_value
            value_series = _df["tmp"]
        value_series = cast("dask_expr.Series", value_series)
        validate_comparand(condition, value_series)

        if self._otherwise_value is None:
            return [value_series.where(condition)]
        try:
            otherwise_series = parse_into_expr(
                self._otherwise_value, namespace=plx
            )._call(df)[0]
        except TypeError:
            # `self._otherwise_value` is a scalar and can't be converted to an expression
            return [value_series.where(condition, self._otherwise_value)]
        validate_comparand(condition, otherwise_series)
        return [value_series.where(condition, otherwise_series)]

    def then(self, value: DaskExpr | Any) -> DaskThen:
        self._then_value = value

        return DaskThen(
            self,
            depth=0,
            function_name="whenthen",
            root_names=None,
            output_names=None,
            returns_scalar=self._returns_scalar,
            backend_version=self._backend_version,
            version=self._version,
        )


class DaskThen(DaskExpr):
    def __init__(
        self,
        call: DaskWhen,
        *,
        depth: int,
        function_name: str,
        root_names: list[str] | None,
        output_names: list[str] | None,
        returns_scalar: bool,
        backend_version: tuple[int, ...],
        version: Version,
    ) -> None:
        self._backend_version = backend_version
        self._version = version
        self._call = call
        self._depth = depth
        self._function_name = function_name
        self._root_names = root_names
        self._output_names = output_names
        self._returns_scalar = returns_scalar

    def otherwise(self, value: DaskExpr | Any) -> DaskExpr:
        # type ignore because we are setting the `_call` attribute to a
        # callable object of type `DaskWhen`, base class has the attribute as
        # only a `Callable`
        self._call._otherwise_value = value  # type: ignore[attr-defined]
        self._function_name = "whenotherwise"
        return self