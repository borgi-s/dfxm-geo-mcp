from dfxm_geo_mcp import runtime


def test_cache_dir_exists():
    d = runtime.cache_dir()
    assert d.exists()


def test_point_kernel_lookup_at_cache():
    runtime.point_kernel_lookup_at_cache()
    import dfxm_geo.direct_space.forward_model as fm

    assert str(runtime.cache_dir()) in str(fm.pkl_fpath)


def test_guard_stdout_redirects_to_stderr(capsys):
    with runtime.guard_stdout():
        print("this must not hit stdout")
    captured = capsys.readouterr()
    assert "this must not hit stdout" not in captured.out
