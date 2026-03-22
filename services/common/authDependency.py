from fastapi import Header, HTTPException
from services.common import auth
import logging


def Authorization(authorization: str = Header(...),Isresearch: str | None = Header(default='false') ):
    if authorization and authorization.startswith("Bearer "):
        access_token = authorization.split(" ")[1]
        try:
            decoded_token = auth.validateToken(access_token)
            print("Is research Explorer USER:",Isresearch)
            user_details = auth.getUserDetail(decoded_token,Isresearch)
            print(f"user_details.... {user_details}")
            return user_details
        except Exception as e:
            logging.exception(f"Invalid Token : {str(e)}")
            raise HTTPException(status_code=401, detail=f"Invalid Token : {str(e)}")
    else:
        raise HTTPException(status_code=401, detail=f"Invalid or missing Token")
def DatasourceAuthorization(authorization: str = Header(...),Isresearch: str | None = Header(default='false') ):
    if authorization and authorization.startswith("Bearer "):
        access_token = authorization.split(" ")[1]
        try:
            decoded_token = auth.validateToken(access_token)

            datasource_details,datasources_backend = auth.getDatasourceDetail(decoded_token,Isresearch)
            print(f"datasource_details.... {datasource_details}")
            return datasource_details,datasources_backend
        except Exception as e:
            logging.exception(f"Invalid Token : {str(e)}")
            raise HTTPException(status_code=401, detail=f"Invalid Token : {str(e)}")
    else:
        raise HTTPException(status_code=401, detail=f"Invalid or missing Token")
    
   