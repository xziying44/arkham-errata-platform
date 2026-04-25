from app.services.image_cache import calc_grid_coords


def test_calc_grid_coords_top_left():
    assert calc_grid_coords(0, 10) == (0, 0, 750, 1050)


def test_calc_grid_coords_first_row():
    result = calc_grid_coords(5, 10)
    assert result == (3750, 0, 4500, 1050)


def test_calc_grid_coords_second_row():
    result = calc_grid_coords(12, 10)
    assert result == (1500, 1050, 2250, 2100)
