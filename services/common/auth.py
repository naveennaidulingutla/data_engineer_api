import jwt
import requests
import os
import logging
from jwt import ExpiredSignatureError, InvalidTokenError
from config import settings
from services.common.utils import source_specific_user_prompts_guide_book

def getPublicKeys(TENANT_ID):
    try:
        url = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"
        response = requests.get(url, timeout=None)
        return response.json()["keys"]
    except Exception as ex:
        logging.info(
            f"Some error occurred while fetching Public Keys. Error Details : {str(ex)}"
        )
        raise


def getUserDetail(decoded_token: dict,isresearch_user: str):
    try:
        user_details = {"email": None, "type": None, "id": None, "name": None}
        user_groups = decoded_token.get("groups", [])
        if len(user_groups) == 0:
            raise Exception("User is not part of required groups")
        if isresearch_user=='true':
            # user_groups.append(os.environ['DE_AIResearchExplorer_User'])
            AI_RESEARCH_EXPLORER_GROUP_ID = os.environ['DE_AIResearchExplorer_User']
            if AI_RESEARCH_EXPLORER_GROUP_ID in user_groups:
                user_details.update({"type": "AI Research Explorer User"})
            else:
                raise Exception("User is not part of required groups")
        else:
            AI_DATA_EXPLORER_GROUP_ID = os.environ["DE_AIDataExplorer_User"]
        
            if AI_DATA_EXPLORER_GROUP_ID in user_groups:
                user_details.update({"type": "AI Data Explorer User"})
            else:
                raise Exception("User is not part of required groups")
        user_details.update({"email": decoded_token.get("preferred_username")})

        user_details.update({"id": decoded_token.get("oid")})

        user_details.update({"name": decoded_token.get("name")})

        return user_details
    except Exception as ex:
        logging.info(
            f"Some error occurred while extracting user details. Error Details : {str(ex)}"
        )
        raise

def get_user_roles(user_groups):
    intern_user = settings.group_ids['DE_Internal_User'] in user_groups
    external_user = settings.group_ids['DE_External_User'] in user_groups
    approver_user = settings.group_ids['DE_Approvers'] in user_groups

    matched_group_names = []

    # Internal / External user
    if intern_user or approver_user:
        matched_group_names.extend(
            key for key, value in settings.internal_group_ids.items() if value in user_groups
        )
    if external_user:
        matched_group_names.extend(
            key for key, value in settings.external_group_ids.items() if value in user_groups
        )

    matched_lower = [name.lower() for name in matched_group_names]

    # Role detection
    survey_user = any("admin" in name or "survey" in name for name in matched_lower)
    sohea_user = any("admin" in name or "sohea" in name for name in matched_lower)
    merative_user = any("admin" in name or "merative" in name for name in matched_lower)
    hcn_user = any("admin" in name or "hcn" in name for name in matched_lower)
    dqddma_user = any("admin" in name or "dqddma" in name or "ddma" in name for name in matched_lower)

    return survey_user,sohea_user, merative_user, hcn_user, dqddma_user


def getDatasourceDetail(decoded_token: dict,isresearch_user: str):
    try:
        user_groups = decoded_token.get("groups", [])
        if not user_groups:
            raise Exception("User is not part of required groups")


        user_info = {
            "name": decoded_token.get("name"),
            "email": decoded_token.get("preferred_username"),
            "id": decoded_token.get("oid"),
            "datasourcesAccess": []
        }

        datasources_backend = []
        print('....',isresearch_user)
        if isresearch_user=='false' or isresearch_user==None:
            survey_user,sohea_user, merative_user, hcn_user,dqddma_user = get_user_roles(user_groups)

            # Define data sources and access control
            data_sources = {
                "ahrf": {"label": "AHRF", "access": survey_user, "description":"Area Health Resources Files with U.S. health workforce and services data."},
                "sohea": {"label": "SOHEA", "access": sohea_user,"description":"State of Oral Health Equity in America (SOHEA) survey."},
                "hpsa": {"label": "HPSA", "access": survey_user,"description":"Medical and Dental U.S. Health Provider Shortage Areas."},
                "merative": {"label": "Merative", "access": merative_user,"description":"Merative dental and medical claims data."},
                "dqddma": {"label": "Dental Claims Data", "access": dqddma_user,"description":"Dental Claims Data"},

                # add hcn ..
            }

            for key, val in data_sources.items():
                user_info["datasourcesAccess"].append(
                    {"label": val["label"], "value": key, "access": val["access"],"description":val['description'],"questions":source_specific_user_prompts_guide_book.get(key)}
                )
                if val["access"]:
                    datasources_backend.append(key)
        else:
            user_info['datasourcesAccess'].append(
                {
                    "label": "Research Explorer",
                    "value":"research",
                    "access":"true",
                    "description":"Research Explorer",
                    "questions":source_specific_user_prompts_guide_book['research']
                }
            )
            datasources_backend.append('research')
        return user_info, datasources_backend

    except Exception as ex:
        logging.info(
            f"Some error occurred while extracting user details. Error Details : {str(ex)}"
        )
        raise

def validateToken(id_token):
    try:
        CLIENT_ID = os.environ["AD_CLIENT_ID"]
        TENANT_ID = os.environ["AD_TENANT_ID"]
        unverified_header = jwt.get_unverified_header(id_token)
        if unverified_header is None:
            raise Exception("Invalid Token header")

        key_id = unverified_header["kid"]

        public_keys = getPublicKeys(TENANT_ID)
        public_key = None
        for key in public_keys:
            if key["kid"] == key_id:
                public_key = key
                break

        if public_key is None:
            raise Exception("Public key not found")

        rsa_key = {
            "kty": public_key["kty"],
            "kid": public_key["kid"],
            "n": public_key["n"],
            "e": public_key["e"],
        }

        public_key_pem = jwt.algorithms.RSAAlgorithm.from_jwk(rsa_key)

        decoded_token = jwt.decode(
            id_token,
            public_key_pem,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=f"https://login.microsoftonline.com/{TENANT_ID}/v2.0",
        )
        return decoded_token
    except ExpiredSignatureError:
        raise Exception("Token has expired")
    except InvalidTokenError:
        raise Exception("Invalid token")
    except Exception as e:
        raise Exception(f"Error validating the token: {str(e)}")
