"""Auth0 access tokens and narrowly scoped service credentials."""
from dataclasses import dataclass
from functools import lru_cache
from secrets import compare_digest
import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.config import get_settings

bearer = HTTPBearer(auto_error=False)

@dataclass(frozen=True)
class Principal:
    sub: str
    permissions: frozenset[str]
    internal: bool = False

    def has(self, permission):
        return not self.internal and permission in self.permissions

@lru_cache(maxsize=4)
def get_jwks_client(domain):
    return jwt.PyJWKClient(f'https://{domain}/.well-known/jwks.json', timeout=5, lifespan=300)

def unauthorized():
    return HTTPException(401, 'Autenticacao necessaria ou token invalido', headers={'WWW-Authenticate':'Bearer'})

def get_principal(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                  x_service_token: str | None = Header(default=None)):
    settings = get_settings()
    if x_service_token is not None:
        secret = settings.internal_api_token
        if len(secret) >= 32 and compare_digest(x_service_token.encode(), secret.encode()):
            return Principal('service:processamento', frozenset(), True)
        raise unauthorized()
    if credentials is None:
        raise unauthorized()
    if not settings.auth0_domain or not settings.auth0_audience:
        raise HTTPException(503, 'Autenticacao nao configurada')
    try:
        if jwt.get_unverified_header(credentials.credentials).get('alg') != 'RS256':
            raise unauthorized()
        key = get_jwks_client(settings.auth0_domain).get_signing_key_from_jwt(credentials.credentials).key
        claims = jwt.decode(credentials.credentials, key, algorithms=['RS256'],
            audience=settings.auth0_audience, issuer=f'https://{settings.auth0_domain}/',
            options={'require':['exp','iss','aud','sub']})
        permissions = claims.get('permissions', [])
        if (not isinstance(claims['sub'], str) or not claims['sub'] or len(claims['sub']) > 150
            or not isinstance(permissions, list) or any(not isinstance(p, str) for p in permissions)
            or claims.get('gty') == 'client-credentials'):
            raise unauthorized()
        return Principal(claims['sub'], frozenset(permissions))
    except jwt.PyJWKClientConnectionError as exc:
        raise HTTPException(503, 'Provedor de autenticacao indisponivel') from exc
    except jwt.PyJWTError as exc:
        raise unauthorized() from exc

def require_permission(permission):
    def dependency(principal: Principal = Depends(get_principal)):
        if not principal.has(permission):
            raise HTTPException(403, 'Permissao insuficiente')
        return principal
    return dependency

def require_internal(principal: Principal = Depends(get_principal)):
    if not principal.internal:
        raise HTTPException(403, 'Operacao exclusiva dos servicos internos')
    return principal

def check_owner(principal, owner, permission='manage:matriculas', allow_internal=False):
    if allow_internal and principal.internal:
        return
    if principal.internal or (principal.sub != owner and not principal.has(permission)):
        raise HTTPException(403, 'Acesso nao permitido a este aluno')
