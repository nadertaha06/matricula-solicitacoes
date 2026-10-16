import time
from types import SimpleNamespace
import pytest
from fastapi import FastAPI, Depends, HTTPException
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

@pytest.fixture
def auth_app(monkeypatch):
    from app import auth
    from app.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, 'auth0_domain', 'tenant.auth0.com')
    monkeypatch.setattr(settings, 'auth0_audience', 'https://matricula-api')
    monkeypatch.setattr(settings, 'internal_api_token', 'a' * 64)
    api = FastAPI()
    @api.get('/identity')
    def identity(principal=Depends(auth.get_principal)):
        return {'sub': principal.sub, 'internal': principal.internal}
    @api.get('/admin')
    def admin(principal=Depends(auth.require_permission('manage:oferta'))):
        return {'ok': True}
    @api.get('/internal')
    def internal(principal=Depends(auth.require_internal)):
        return {'ok': True}
    return auth, TestClient(api)

@pytest.fixture
def token_factory(auth_app, monkeypatch):
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    auth, _ = auth_app
    monkeypatch.setattr(auth, 'get_jwks_client', lambda domain: SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=key.public_key())))
    def make(**changes):
        claims = dict(sub='auth0|aluno', iss='https://tenant.auth0.com/',
                      aud='https://matricula-api', exp=int(time.time()) + 300, permissions=[])
        claims.update(changes)
        return jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'test'})
    return make

def test_requires_authentication(auth_app):
    _, client = auth_app
    assert client.get('/identity').status_code == 401
    assert client.get('/identity', headers={'Authorization': 'Bearer malformed'}).status_code == 401

def test_valid_token_and_permission(auth_app, token_factory):
    _, client = auth_app
    headers = {'Authorization': 'Bearer ' + token_factory()}
    assert client.get('/identity', headers=headers).json() == {'sub':'auth0|aluno', 'internal':False}
    assert client.get('/admin', headers=headers).status_code == 403
    headers = {'Authorization': 'Bearer ' + token_factory(permissions=['manage:oferta'])}
    assert client.get('/admin', headers=headers).status_code == 200
    assert client.get('/internal', headers=headers).status_code == 403

@pytest.mark.parametrize('changes', [dict(exp=1), dict(iss='https://wrong/'), dict(aud='wrong'), dict(sub=''), dict(permissions='manage:oferta')])
def test_invalid_claims(auth_app, token_factory, changes):
    _, client = auth_app
    assert client.get('/identity', headers={'Authorization': 'Bearer ' + token_factory(**changes)}).status_code == 401

def test_internal_token_not_an_administrator(auth_app):
    _, client = auth_app
    headers = {'X-Service-Token': 'a' * 64}
    assert client.get('/internal', headers=headers).status_code == 200
    assert client.get('/admin', headers=headers).status_code == 403
    assert client.get('/identity', headers={'X-Service-Token':'bad'}).status_code == 401

def test_owner_permissions():
    from app.auth import Principal, check_owner
    student = Principal('a', frozenset())
    check_owner(student, 'a')
    with pytest.raises(HTTPException) as error:
        check_owner(student, 'b')
    assert error.value.status_code == 403
    check_owner(Principal('admin', frozenset({'manage:matriculas'})), 'b')
    check_owner(Principal('worker', frozenset(), True), 'b', allow_internal=True)

def test_missing_configuration_fails_closed(auth_app, monkeypatch):
    from app.config import get_settings
    _, client = auth_app
    monkeypatch.setattr(get_settings(), 'auth0_domain', '')
    assert client.get('/identity', headers={'Authorization':'Bearer token'}).status_code == 503


def test_tampered_signature_is_rejected(auth_app, token_factory):
    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa
    _, client = auth_app
    claims = jwt.decode(token_factory(), options={'verify_signature':False})
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = jwt.encode(claims, other_key, algorithm='RS256')
    assert client.get('/identity', headers={'Authorization':'Bearer '+token}).status_code == 401


def test_jwks_outage_returns_503(auth_app, token_factory, monkeypatch):
    import jwt
    auth, client = auth_app
    token = token_factory()
    def unavailable(domain):
        raise jwt.PyJWKClientConnectionError('offline')
    monkeypatch.setattr(auth, 'get_jwks_client', unavailable)
    assert client.get('/identity', headers={'Authorization':'Bearer '+token}).status_code == 503


def test_missing_exp_and_symmetric_algorithm_rejected(auth_app, token_factory):
    import jwt
    _, client = auth_app
    token = jwt.encode({'sub':'a'}, 'test-secret-with-at-least-32-bytes', algorithm='HS256')
    assert client.get('/identity', headers={'Authorization':'Bearer '+token}).status_code == 401
    assert client.get('/identity', headers={'Authorization':'Bearer '+token_factory(gty='client-credentials')}).status_code == 401
