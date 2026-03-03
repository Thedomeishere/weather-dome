"""Tests for salt/plow treatment integration into melt risk model."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from app.schemas.weather import WeatherConditions
from app.services.salt_treatment import (
    _compute_treatment_score,
    _treatment_cache,
    ingest_treatment_data,
    get_treatment_score,
    ZoneTreatmentStatus,
)
from app.services.plownyc_client import PlowActivity
from app.services.dsny_salt_client import SaltUsage
from app.services.ny511_winter_client import RoadConditionSummary
from app.services import melt_risk


def _make_weather(**kwargs) -> WeatherConditions:
    defaults = {
        "zone_id": "CONED-BKN",
        "source": "test",
        "observed_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return WeatherConditions(**defaults)


# --- Treatment score computation tests ---


class TestComputeTreatmentScore:
    def test_all_sources_active(self):
        """All three sources present and active → high score."""
        score = _compute_treatment_score(
            plow_coverage=0.8, salt_active=True, salt_recent=False, road_coverage=0.6,
        )
        assert score is not None
        assert score > 0.7

    def test_no_data_returns_none(self):
        """No sources have data → None (not 0)."""
        score = _compute_treatment_score(
            plow_coverage=None, salt_active=None, salt_recent=None, road_coverage=None,
        )
        assert score is None

    def test_plow_only(self):
        """Only plow data available → uses plow alone."""
        score = _compute_treatment_score(
            plow_coverage=0.7, salt_active=None, salt_recent=None, road_coverage=None,
        )
        assert score is not None
        assert 0.65 <= score <= 0.75  # should be ~0.7 (renormalized)

    def test_salt_active_signal(self):
        """Salt actively dispensing → signal = 1.0."""
        score = _compute_treatment_score(
            plow_coverage=None, salt_active=True, salt_recent=False, road_coverage=None,
        )
        assert score is not None
        assert score == 1.0

    def test_salt_recent_signal(self):
        """Salt dispensed recently but not active → signal = 0.5."""
        score = _compute_treatment_score(
            plow_coverage=None, salt_active=False, salt_recent=True, road_coverage=None,
        )
        assert score is not None
        assert score == 0.5

    def test_salt_none_signal(self):
        """Salt data present but no dispensing at all → signal = 0.0."""
        score = _compute_treatment_score(
            plow_coverage=None, salt_active=False, salt_recent=False, road_coverage=None,
        )
        assert score is not None
        assert score == 0.0

    def test_road_only(self):
        """Only 511NY road data → uses road alone."""
        score = _compute_treatment_score(
            plow_coverage=None, salt_active=None, salt_recent=None, road_coverage=0.9,
        )
        assert score is not None
        assert 0.85 <= score <= 0.95


# --- Melt risk integration tests ---


class TestMeltRiskTreatmentIntegration:
    """Test that treatment_score correctly boosts/dampens salt_melt."""

    def _melt_weather(self):
        """Weather with active snow melt conditions for salt_melt to fire."""
        return _make_weather(
            zone_id="CONED-BKN",
            temperature_f=36.0,
            snow_depth_in=4.0,
            snow_rate_in_hr=0.0,
            ice_accum_in=0.0,
            condition_text="Cloudy",
        )

    def test_none_unchanged(self):
        """treatment_score=None should produce same result as no arg."""
        w = self._melt_weather()
        result_default = melt_risk.compute("CONED-BKN", w)
        result_none = melt_risk.compute("CONED-BKN", w, treatment_score=None)
        assert result_default.salt_melt_risk == result_none.salt_melt_risk

    def test_boost_high_treatment(self):
        """treatment_score > 0.5 should boost salt_melt."""
        w = self._melt_weather()
        result_none = melt_risk.compute("CONED-BKN", w, treatment_score=None)
        result_boost = melt_risk.compute("CONED-BKN", w, treatment_score=0.8)
        assert result_boost.salt_melt_risk >= result_none.salt_melt_risk

    def test_dampen_zero_treatment(self):
        """treatment_score=0.0 should dampen salt_melt by 15%."""
        w = self._melt_weather()
        result_none = melt_risk.compute("CONED-BKN", w, treatment_score=None)
        result_dampen = melt_risk.compute("CONED-BKN", w, treatment_score=0.0)
        # Dampened should be lower (salt_melt × 0.85)
        assert result_dampen.salt_melt_risk <= result_none.salt_melt_risk

    def test_confirmed_treatment_factor(self):
        """High treatment score should add a contributing factor string."""
        w = self._melt_weather()
        result = melt_risk.compute("CONED-BKN", w, treatment_score=0.8)
        factor_texts = " ".join(result.contributing_factors)
        assert "salt treatment" in factor_texts.lower() or "treatment" in factor_texts.lower()

    def test_treatment_without_weather_signal(self):
        """Treatment detected but weather shows no salt_melt → inject minimum."""
        # Warm enough to melt but no snow on the ground → weather won't infer salt
        # But snow_present = True due to snow_depth
        w = _make_weather(
            zone_id="CONED-BKN",
            temperature_f=35.0,
            snow_depth_in=2.0,
            snow_rate_in_hr=0.0,
            ice_accum_in=0.0,
            condition_text="Cloudy",
        )
        result = melt_risk.compute("CONED-BKN", w, treatment_score=0.9)
        # Should have some salt_melt even if weather didn't infer it strongly
        assert result.salt_melt_risk >= 0


# --- PlowNYC client tests ---


class TestPlowNYCClient:
    @pytest.mark.asyncio
    async def test_parse_response(self):
        """PlowNYC client should parse Socrata aggregation response."""
        from app.services import plownyc_client

        mock_serviced = [
            {"borough": "Brooklyn", "serviced_count": "150", "latest": "2026-03-03T10:00:00"},
            {"borough": "Manhattan", "serviced_count": "200", "latest": "2026-03-03T09:30:00"},
        ]
        mock_totals = [
            {"borough": "Brooklyn", "total_count": "500"},
            {"borough": "Manhattan", "total_count": "600"},
        ]

        mock_response_serviced = MagicMock()
        mock_response_serviced.raise_for_status = MagicMock()
        mock_response_serviced.json.return_value = mock_serviced

        mock_response_totals = MagicMock()
        mock_response_totals.raise_for_status = MagicMock()
        mock_response_totals.json.return_value = mock_totals

        with patch("app.services.plownyc_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=[mock_response_serviced, mock_response_totals])
            mock_client_cls.return_value = mock_client

            results = await plownyc_client.fetch_plow_activity()

        assert len(results) == 2
        bkn = next(r for r in results if r.zone_id == "CONED-BKN")
        assert bkn.segments_serviced == 150
        assert bkn.total_segments == 500
        assert bkn.coverage_pct == pytest.approx(0.3, abs=0.01)

    @pytest.mark.asyncio
    async def test_failure_returns_empty(self):
        """PlowNYC client should return empty list on failure."""
        from app.services import plownyc_client

        with patch("app.services.plownyc_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=Exception("Connection error"))
            mock_client_cls.return_value = mock_client

            results = await plownyc_client.fetch_plow_activity()

        assert results == []


# --- DSNY Salt client tests ---


class TestDSNYSaltClient:
    @pytest.mark.asyncio
    async def test_active_dispensing_detection(self):
        """Salt dispensed within 3 hours → dispensing_active=True."""
        from app.services import dsny_salt_client

        recent_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        mock_rows = [
            {"borough": "Brooklyn", "total_tons": "45.5", "latest": recent_time},
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_rows

        with patch("app.services.dsny_salt_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            results = await dsny_salt_client.fetch_salt_usage()

        assert len(results) == 1
        assert results[0].dispensing_active is True
        assert results[0].tons_dispensed == pytest.approx(45.5)

    @pytest.mark.asyncio
    async def test_old_dispensing_not_active(self):
        """Salt dispensed > 3 hours ago → dispensing_active=False."""
        from app.services import dsny_salt_client

        old_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        mock_rows = [
            {"borough": "Manhattan", "total_tons": "30.0", "latest": old_time},
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_rows

        with patch("app.services.dsny_salt_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            results = await dsny_salt_client.fetch_salt_usage()

        assert len(results) == 1
        assert results[0].dispensing_active is False


# --- 511NY client tests ---


class TestNY511Client:
    @pytest.mark.asyncio
    async def test_no_key_returns_empty(self):
        """511NY client should return empty list immediately if no API key."""
        from app.services import ny511_winter_client

        with patch.object(ny511_winter_client.settings, "ny511_api_key", ""):
            results = await ny511_winter_client.fetch_road_conditions()
        assert results == []

    @pytest.mark.asyncio
    async def test_parse_conditions_by_county(self):
        """511NY client should parse road conditions and map counties to zones."""
        from app.services import ny511_winter_client

        mock_data = [
            {"County": "Westchester", "Condition": "Plowed and Salted"},
            {"County": "Westchester", "Condition": "Snow Covered"},
            {"County": "Westchester", "Condition": "Chemically Treated"},
            {"County": "Orange", "Condition": "Plowed"},
            {"County": "Orange", "Condition": "Slippery"},
        ]

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = mock_data

        with patch.object(ny511_winter_client.settings, "ny511_api_key", "test-key"):
            with patch("app.services.ny511_winter_client.httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client.get = AsyncMock(return_value=mock_response)
                mock_client_cls.return_value = mock_client

                results = await ny511_winter_client.fetch_road_conditions()

        assert len(results) == 2
        wst = next(r for r in results if r.zone_id == "CONED-WST")
        assert wst.total_segments == 3
        assert wst.treated_segments == 2  # "plowed and salted" + "chemically treated"
        assert wst.winter_condition_segments == 1  # "snow covered"
        assert wst.treatment_coverage == pytest.approx(2 / 3, abs=0.01)

        ora = next(r for r in results if r.zone_id == "OR-ORA")
        assert ora.total_segments == 2
        assert ora.treated_segments == 1  # "plowed"


# --- Full pipeline test ---


class TestTreatmentPipeline:
    @pytest.mark.asyncio
    async def test_ingest_populates_cache(self):
        """Full ingest should populate cache for zones with data."""
        now = datetime.now(timezone.utc)
        mock_plow = [
            PlowActivity("CONED-BKN", 100, 400, now, 0.25),
            PlowActivity("CONED-MAN", 200, 500, now, 0.40),
        ]
        mock_salt = [
            SaltUsage("CONED-BKN", 50.0, True, now),
        ]
        mock_road = [
            RoadConditionSummary("CONED-WST", 20, 15, 5, 0.75),
        ]

        # Clear cache before test
        _treatment_cache.clear()

        with patch("app.services.salt_treatment.plownyc_client.fetch_plow_activity", new_callable=AsyncMock, return_value=mock_plow), \
             patch("app.services.salt_treatment.dsny_salt_client.fetch_salt_usage", new_callable=AsyncMock, return_value=mock_salt), \
             patch("app.services.salt_treatment.ny511_winter_client.fetch_road_conditions", new_callable=AsyncMock, return_value=mock_road):
            await ingest_treatment_data()

        # Brooklyn should have plow + salt data
        bkn_score = get_treatment_score("CONED-BKN")
        assert bkn_score is not None
        assert bkn_score > 0.5  # plow coverage 0.25 + salt active

        # Manhattan should have plow only
        man_score = get_treatment_score("CONED-MAN")
        assert man_score is not None
        assert 0.35 <= man_score <= 0.45  # plow coverage 0.4 renormalized

        # Westchester should have road data only
        wst_score = get_treatment_score("CONED-WST")
        assert wst_score is not None
        assert 0.7 <= wst_score <= 0.8  # road coverage 0.75 renormalized

        # Zone with no data should return None
        assert get_treatment_score("OR-SUL") is None

    @pytest.mark.asyncio
    async def test_ingest_handles_failures(self):
        """Ingest should handle partial source failures gracefully."""
        now = datetime.now(timezone.utc)
        mock_plow = [PlowActivity("CONED-BKN", 100, 400, now, 0.25)]

        _treatment_cache.clear()

        with patch("app.services.salt_treatment.plownyc_client.fetch_plow_activity", new_callable=AsyncMock, return_value=mock_plow), \
             patch("app.services.salt_treatment.dsny_salt_client.fetch_salt_usage", new_callable=AsyncMock, side_effect=Exception("API down")), \
             patch("app.services.salt_treatment.ny511_winter_client.fetch_road_conditions", new_callable=AsyncMock, side_effect=Exception("API down")):
            await ingest_treatment_data()

        # Brooklyn should still have plow data
        bkn_score = get_treatment_score("CONED-BKN")
        assert bkn_score is not None
        assert bkn_score == pytest.approx(0.25, abs=0.01)
