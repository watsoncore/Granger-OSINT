import threading

import httpx
import pytest

from grangerpet.geoint.images import GeointError
from grangerpet.geoint.mapping import MappingClient, coordinates, reverse_search_providers, DEFAULT_NOMINATIM, DEFAULT_OVERPASS


def test_default_osm_endpoints_are_bounded_public_clients_without_key():
    client = MappingClient()
    assert client.readiness("map_geocode")["state"] == "ready_local"
    assert client.readiness("map_overpass")["available"] is True
    assert client.readiness("map_wikimedia")["state"] == "ready_local"
    assert client.nominatim_endpoint == DEFAULT_NOMINATIM
    assert client.overpass_endpoint == DEFAULT_OVERPASS


@pytest.mark.parametrize("value", ["nan,0", "1,inf", "91,0", "0,181", "0,0,0", "https://example.org", "1;DROP,2"])
def test_coordinates_strictly_validated(value):
    with pytest.raises(GeointError):
        coordinates(value)


def test_commons_real_request_shape_attribution_and_cache():
    requests = []
    def handler(request):
        requests.append(request)
        assert request.headers["User-Agent"].startswith("Granger-OSINT/")
        assert request.url.params["gsnamespace"] == "6"
        assert request.url.params["gslimit"] == "20"
        return httpx.Response(200, json={"query": {"geosearch": [{"pageid": 1, "title": "File:Unit fixture.jpg", "lat": 51.5, "lon": -.125, "dist": 20}]}})
    client = MappingClient(transport=httpx.MockTransport(handler))
    result = client.execute("map_wikimedia", "51.5,-.125")
    assert result["status"] == "completed" and result["cached"] is False
    assert result["media"][0]["page_id"] == 1 and "licences" in result["attribution"]
    assert client.execute("map_wikimedia", "51.5,-.125")["cached"] is True
    assert len(requests) == 1


def test_overpass_query_is_fixed_bounded_not_arbitrary_code():
    def handler(request):
        query = request.url.params["data"]
        assert "[timeout:10]" in query and "[maxsize:1048576]" in query and "out center 20" in query
        return httpx.Response(200, json={"elements": [{"type": "node", "id": 1, "lat": 51.5, "lon": -.125, "tags": {"name": "Fixture"}}]})
    client = MappingClient(overpass_endpoint="https://overpass.example/api/interpreter", transport=httpx.MockTransport(handler))
    result = client.execute("map_overpass", "51.5,-.125")
    assert result["objects"][0]["url"] == "https://www.openstreetmap.org/node/1"
    assert "OpenStreetMap" in result["attribution"]
    with pytest.raises(GeointError):
        client.execute("map_overpass", "[out:json];node;out;")


@pytest.mark.parametrize("status,code", [(403, "access_denied"), (401, "access_denied"), (429, "rate_limited"), (500, "service_unavailable"), (302, "http_error")])
def test_http_failures_are_not_successful_results(status, code):
    client = MappingClient(transport=httpx.MockTransport(lambda request: httpx.Response(status, text="private server diagnostic")))
    with pytest.raises(GeointError) as error:
        client.execute("map_wikimedia", "51.5,-.125")
    assert error.value.code == code and "private" not in str(error.value)


def test_429_blocks_immediate_retry_without_another_request():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(429, headers={"Retry-After": "30"})
    client = MappingClient(transport=httpx.MockTransport(handler))
    for _ in range(2):
        with pytest.raises(GeointError) as error:
            client.execute("map_wikimedia", "51.5,-.125")
        assert error.value.code == "rate_limited"
    assert len(requests) == 1


def test_geocoder_empty_config_uses_public_default_and_validates_actual_schema():
    requests=[]
    def handler(request):
        requests.append(request)
        assert request.url.host=="nominatim.openstreetmap.org"
        assert request.url.params["limit"]=="5" and request.url.params["q"]=="London"
        assert "Authorization" not in request.headers
        return httpx.Response(200,json=[{"lat":"51.5","lon":"-.125","osm_type":"relation","osm_id":1,"display_name":"Fixture London"},
            {"lat":"nan","lon":"-.125","osm_type":"node","osm_id":2,"display_name":"Invalid"}])
    client=MappingClient(nominatim_endpoint="",transport=httpx.MockTransport(handler))
    result=client.execute("map_geocode","London")
    assert len(result["places"])==1 and result["places"][0]["latitude"]==51.5
    assert result["usage_policy"].endswith("nominatim/") and "OpenStreetMap" in result["attribution"]
    assert client.execute("map_geocode","London")["cached"] and len(requests)==1


def test_hourly_public_geocoder_budget_blocks_before_network_but_cache_remains_available():
    import time
    requests=[]
    client=MappingClient(transport=httpx.MockTransport(lambda request:(requests.append(request) or httpx.Response(200,json=[]))))
    client.execute("map_geocode","London")
    client._request_times["nominatim.openstreetmap.org"].extend([time.monotonic()]*29)
    assert client.execute("map_geocode","London")["cached"]
    with pytest.raises(GeointError) as error:
        client.execute("map_geocode","Paris")
    assert error.value.code=="rate_limited" and len(requests)==1


def test_server_failure_sets_bounded_backoff_and_does_not_retry_blindly():
    requests=[]
    client=MappingClient(transport=httpx.MockTransport(lambda request:(requests.append(request) or httpx.Response(503))))
    for code in ("service_unavailable","rate_limited"):
        with pytest.raises(GeointError) as error:
            client.execute("map_overpass","51.5,-.125")
        assert error.value.code==code
    assert len(requests)==1


@pytest.mark.parametrize("tool,query,payload",[("map_geocode","London",[{"changed_schema":True}]),
    ("map_overpass","51.5,-.125",{"elements":[{"changed_schema":True}]}),
    ("map_wikimedia","51.5,-.125",{"query":{"geosearch":[{"changed_schema":True}]}})])
def test_changed_nonempty_mapping_schema_is_an_error_not_a_fabricated_empty_success(tool,query,payload):
    client=MappingClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=payload)))
    with pytest.raises(GeointError) as error:
        client.execute(tool,query)
    assert error.value.code=="invalid_response"


def test_cancelled_geographic_lookup_never_calls_network():
    event = threading.Event()
    event.set()
    def handler(_):
        raise AssertionError("Cancelled operation must not send data")
    client = MappingClient(transport=httpx.MockTransport(handler))
    with pytest.raises(GeointError) as error:
        client.execute("map_wikimedia", "51.5,-.125", event)
    assert error.value.code == "cancelled"


def test_timeout_and_invalid_json():
    def handler(request):
        raise httpx.ReadTimeout("private diagnostic", request=request)
    client = MappingClient(transport=httpx.MockTransport(handler))
    with pytest.raises(GeointError) as error:
        client.execute("map_wikimedia", "51.5,-.125")
    assert error.value.code == "timeout"
    client = MappingClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text="not JSON")))
    with pytest.raises(GeointError) as error:
        client.execute("map_wikimedia", "51.5,-.125")
    assert error.value.code == "invalid_response"


def test_reverse_search_catalogue_is_not_fabricated_execution():
    providers = reverse_search_providers()
    assert len(providers) == 4
    assert all(item["automated"] is False for item in providers)
    assert {item["mode"] for item in providers} <= {"manual_handoff", "unavailable"}
    assert next(item for item in providers if item["id"] == "bing_visual_search")["mode"] == "unavailable"
