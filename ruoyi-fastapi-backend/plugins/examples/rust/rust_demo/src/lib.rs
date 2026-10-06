//! 交付 wheel 包含编译后的原生扩展，Rust 源码保留在开发工程中。
use pyo3::prelude::*;
use pyo3::types::PyDict;

/// 声明 ASGI 子应用工厂，资源初始化由宿主驱动的生命周期负责。
#[pyfunction]
fn create_plugin<'py>(py: Python<'py>, _host: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let kwargs = PyDict::new(py);
    kwargs.set_item("app_factory", wrap_pyfunction!(create_app, py)?)?;
    py.import("plugins.core.sdk")?
        .getattr("PluginDefinition")?
        .call((), Some(&kwargs))
}

/// 演示以显式路由声明方式接入宿主，并使用独立权限保护接口。
#[pyfunction]
fn create_router_plugin<'py>(
    py: Python<'py>,
    _host: Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let router = py.import("fastapi")?.getattr("APIRouter")?.call0()?;
    add_routes(py, &router, "/rust_demo")?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("routers", vec![router])?;
    py.import("plugins.core.sdk")?
        .getattr("PluginDefinition")?
        .call((), Some(&kwargs))
}

/// 为当前 worker 创建子应用，并绑定原生启动、关闭回调和业务路由。
#[pyfunction]
fn create_app<'py>(py: Python<'py>, host: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let sdk = py.import("plugins.core.sdk")?;
    let lifespan = sdk.getattr("plugin_lifespan")?.call1((
        host,
        wrap_pyfunction!(startup, py)?,
        wrap_pyfunction!(shutdown, py)?,
    ))?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("title", "Rust native plugin")?;
    kwargs.set_item("lifespan", lifespan)?;
    kwargs.set_item("docs_url", py.None())?;
    kwargs.set_item("redoc_url", py.None())?;
    let app = py
        .import("fastapi")?
        .getattr("FastAPI")?
        .call((), Some(&kwargs))?;
    add_routes(py, &app, "")?;
    Ok(app)
}

/// 通过宿主 SDK 包装接口权限，供子应用和显式路由两种模式复用。
fn add_routes(py: Python<'_>, app: &Bound<'_, PyAny>, prefix: &str) -> PyResult<()> {
    let sdk = py.import("plugins.core.sdk")?;
    for (path, permission, callback, summary, description) in [
        (
            "/api/info",
            "rust_demo:view",
            wrap_pyfunction!(info, py)?,
            "获取原生插件信息接口",
            "用于获取当前插件标识、宿主API版本、运行引擎和服务器时间",
        ),
        (
            "/api/profile",
            "rust_demo:profile",
            wrap_pyfunction!(profile, py)?,
            "获取原生插件当前用户信息接口",
            "用于通过宿主服务获取当前登录用户的基本信息",
        ),
    ] {
        let options = PyDict::new(py);
        options.set_item("permission", permission)?;
        let endpoint = sdk
            .getattr("plugin_endpoint")?
            .call((callback,), Some(&options))?;
        let route_options = PyDict::new(py);
        route_options.set_item("summary", summary)?;
        route_options.set_item("description", description)?;
        route_options.set_item("response_model", py.get_type::<PyDict>())?;
        app.call_method(
            "add_api_route",
            (format!("{prefix}{path}"), endpoint),
            Some(&route_options),
        )?;
    }
    Ok(())
}

/// 记录插件启动，并通过 Python 可等待对象返回就绪状态。
#[pyfunction]
fn startup<'py>(py: Python<'py>, host: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    host.getattr("logger")?
        .call_method1("info", ("Rust plugin started",))?;
    pyo3_async_runtimes::tokio::future_into_py(py, async {
        Python::attach(|py| {
            let state = PyDict::new(py);
            state.set_item("nativeReady", true)?;
            Ok(state.unbind())
        })
    })
}

/// 演示插件关闭回调；插件只负责释放自己创建的资源。
#[pyfunction]
fn shutdown<'py>(py: Python<'py>, host: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    host.getattr("logger")?
        .call_method1("info", ("Rust plugin stopped",))?;
    pyo3_async_runtimes::tokio::future_into_py(py, async { Ok(()) })
}

/// 通过可等待对象返回健康结果，供宿主统一处理原生异步回调。
#[pyfunction]
fn health<'py>(py: Python<'py>, _context: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    pyo3_async_runtimes::tokio::future_into_py(py, async { Ok(true) })
}

#[pyfunction]
fn info<'py>(py: Python<'py>, context: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let host = context.getattr("host")?;
    let plugin_id: String = host.getattr("plugin_id")?.extract()?;
    let api_version: String = host.getattr("api_version")?.extract()?;
    // 在当前 Python 调用线程中复用宿主时间工具，再将普通字符串交给异步任务。
    let timestamp: String = py
        .import("utils.time_util")?
        .getattr("TimezoneUtil")?
        .call_method0("utc_now")?
        .call_method0("isoformat")?
        .extract()?;
    pyo3_async_runtimes::tokio::future_into_py(py, async move {
        Python::attach(|py| {
            let result = PyDict::new(py);
            result.set_item("pluginId", plugin_id)?;
            result.set_item("hostApiVersion", api_version)?;
            result.set_item("engine", "rust")?;
            result.set_item("serverTime", timestamp)?;
            Ok(result.unbind())
        })
    })
}

#[pyfunction]
fn profile<'py>(_py: Python<'py>, context: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    // 请求取消和数据库会话生命周期继续由宿主事件循环管理，不能阻塞等待或调用 asyncio.run。
    context
        .getattr("host")?
        .call_method1("service", ("users.current_profile.v1",))?
        .call1((context,))
}

/// 演示原生后台任务读取宿主任务上下文并返回执行结果。
#[pyfunction]
fn heartbeat<'py>(py: Python<'py>, context: Bound<'py, PyAny>) -> PyResult<Bound<'py, PyAny>> {
    let job_id: String = context.getattr("job_id")?.extract()?;
    context
        .getattr("host")?
        .getattr("logger")?
        .call_method1("info", (format!("Rust background job: {job_id}"),))?;
    pyo3_async_runtimes::tokio::future_into_py(py, async move { Ok(job_id) })
}

/// 导出清单和宿主运行时需要的 Python 扩展入口。
#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(create_plugin, module)?)?;
    module.add_function(wrap_pyfunction!(create_router_plugin, module)?)?;
    module.add_function(wrap_pyfunction!(create_app, module)?)?;
    module.add_function(wrap_pyfunction!(health, module)?)?;
    module.add_function(wrap_pyfunction!(profile, module)?)?;
    module.add_function(wrap_pyfunction!(heartbeat, module)?)?;
    Ok(())
}
