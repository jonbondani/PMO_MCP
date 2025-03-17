import os
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify
from requests.auth import HTTPBasicAuth

app = Flask(__name__)

# Configuración de credenciales
JIRA_URL = os.environ.get("JIRA_URL", "https://your-domain.atlassian.net")
JIRA_USERNAME = os.environ.get("JIRA_USERNAME", "your-email@example.com")
JIRA_API_TOKEN = os.environ.get("JIRA_API_TOKEN", "your-api-token")
CONFLUENCE_URL = os.environ.get("CONFLUENCE_URL", "https://your-domain.atlassian.net/wiki")
CONFLUENCE_USERNAME = os.environ.get("CONFLUENCE_USERNAME", "your-email@example.com")
CONFLUENCE_API_TOKEN = os.environ.get("CONFLUENCE_API_TOKEN", "your-api-token")

# Autenticación
jira_auth = HTTPBasicAuth(JIRA_USERNAME, JIRA_API_TOKEN)
confluence_auth = HTTPBasicAuth(CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN)

# Headers para las solicitudes
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json"
}

@app.route('/context', methods=['POST'])
def get_context():
    request_data = request.json
    
    # Extraer información del sprint
    sprint_id = request_data.get('sprint_id')
    if not sprint_id:
        return jsonify({"error": "Se requiere el ID del sprint"}), 400
    
    # Obtener datos del sprint desde Jira
    sprint_data = get_sprint_data(sprint_id)
    if not sprint_data:
        return jsonify({"error": "No se pudo obtener la información del sprint"}), 404
    
    # Obtener issues del sprint
    sprint_issues = get_sprint_issues(sprint_id)
    
    # Analizar métricas del sprint
    sprint_metrics = analyze_sprint_metrics(sprint_issues, sprint_data)
    
    # Contexto combinado para el agente
    context = {
        "sprint": sprint_data,
        "issues": sprint_issues,
        "metrics": sprint_metrics
    }
    
    return jsonify(context)

@app.route('/update-confluence', methods=['POST'])
def update_confluence_doc():
    request_data = request.json
    
    # Extraer información necesaria
    sprint_id = request_data.get('sprint_id')
    confluence_page_id = request_data.get('confluence_page_id')
    sprint_insights = request_data.get('sprint_insights')
    
    if not all([sprint_id, confluence_page_id, sprint_insights]):
        return jsonify({"error": "Se requieren sprint_id, confluence_page_id y sprint_insights"}), 400
    
    # Actualizar documento de Confluence
    result = update_confluence_document(confluence_page_id, sprint_insights)
    
    return jsonify(result)

def get_sprint_data(sprint_id):
    """Obtiene los detalles del sprint desde Jira"""
    url = f"{JIRA_URL}/rest/agile/1.0/sprint/{sprint_id}"
    
    try:
        response = requests.get(url, auth=jira_auth, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener datos del sprint: {e}")
        return None

def get_sprint_issues(sprint_id):
    """Obtiene todas las issues del sprint"""
    url = f"{JIRA_URL}/rest/agile/1.0/sprint/{sprint_id}/issue"
    
    all_issues = []
    start_at = 0
    max_results = 50
    
    try:
        while True:
            params = {
                "startAt": start_at,
                "maxResults": max_results,
                "fields": "summary,status,issuetype,priority,assignee,created,updated,resolutiondate,customfield_10016"  # customfield_10016 es story points
            }
            
            response = requests.get(url, auth=jira_auth, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            
            if not data.get('issues'):
                break
                
            all_issues.extend(data['issues'])
            
            if len(data['issues']) < max_results:
                break
                
            start_at += max_results
            
        return all_issues
    except requests.exceptions.RequestException as e:
        print(f"Error al obtener issues del sprint: {e}")
        return []

def analyze_sprint_metrics(issues, sprint_data):
    """Analiza las métricas del sprint basado en sus issues"""
    
    # Métricas a recopilar
    metrics = {
        "total_issues": len(issues),
        "issues_by_status": {},
        "issues_by_type": {},
        "issues_by_assignee": {},
        "story_points": {
            "total": 0,
            "completed": 0
        },
        "sprint_progress": 0,
        "sprint_dates": {
            "start_date": sprint_data.get("startDate"),
            "end_date": sprint_data.get("endDate")
        }
    }
    
    # Analizar issues
    for issue in issues:
        # Contar por estado
        status = issue['fields']['status']['name']
        metrics['issues_by_status'][status] = metrics['issues_by_status'].get(status, 0) + 1
        
        # Contar por tipo
        issue_type = issue['fields']['issuetype']['name']
        metrics['issues_by_type'][issue_type] = metrics['issues_by_type'].get(issue_type, 0) + 1
        
        # Contar por asignado
        assignee = issue['fields'].get('assignee', {}).get('displayName', 'Unassigned')
        metrics['issues_by_assignee'][assignee] = metrics['issues_by_assignee'].get(assignee, 0) + 1
        
        # Contar story points
        story_points = issue['fields'].get('customfield_10016', 0) or 0
        metrics['story_points']['total'] += story_points
        
        # Contar story points completados
        if status in ['Done', 'Closed', 'Resolved']:
            metrics['story_points']['completed'] += story_points
    
    # Calcular progreso del sprint
    if metrics['story_points']['total'] > 0:
        metrics['sprint_progress'] = (metrics['story_points']['completed'] / metrics['story_points']['total']) * 100
    
    # Calcular estadísticas de velocidad
    metrics['velocity'] = metrics['story_points']['completed']
    
    return metrics

def update_confluence_document(page_id, sprint_insights):
    """Actualiza un documento de Confluence con los insights del sprint"""
    url = f"{CONFLUENCE_URL}/rest/api/content/{page_id}"
    
    try:
        # Primero, obtener la versión actual del documento
        response = requests.get(url, auth=confluence_auth, headers=headers)
        response.raise_for_status()
        
        page_data = response.json()
        current_version = page_data['version']['number']
        
        # Crear el contenido actualizado
        today = datetime.now().strftime("%Y-%m-%d")
        
        content = {
            "type": "page",
            "title": page_data['title'],
            "version": {
                "number": current_version + 1
            },
            "body": {
                "storage": {
                    "value": f"""
                        <h1>Sprint Insights - Actualizado el {today}</h1>
                        
                        <h2>Resumen</h2>
                        <p>ID del Sprint: {sprint_insights['sprint']['id']}</p>
                        <p>Nombre del Sprint: {sprint_insights['sprint']['name']}</p>
                        <p>Fecha de inicio: {sprint_insights['metrics']['sprint_dates']['start_date']}</p>
                        <p>Fecha de finalización: {sprint_insights['metrics']['sprint_dates']['end_date']}</p>
                        
                        <h2>Métricas</h2>
                        <p>Total de issues: {sprint_insights['metrics']['total_issues']}</p>
                        <p>Story points totales: {sprint_insights['metrics']['story_points']['total']}</p>
                        <p>Story points completados: {sprint_insights['metrics']['story_points']['completed']}</p>
                        <p>Progreso del sprint: {sprint_insights['metrics']['sprint_progress']:.2f}%</p>
                        <p>Velocidad: {sprint_insights['metrics']['velocity']}</p>
                        
                        <h2>Distribución por estado</h2>
                        <ul>
                            {generate_list_items(sprint_insights['metrics']['issues_by_status'])}
                        </ul>
                        
                        <h2>Distribución por tipo</h2>
                        <ul>
                            {generate_list_items(sprint_insights['metrics']['issues_by_type'])}
                        </ul>
                        
                        <h2>Distribución por asignado</h2>
                        <ul>
                            {generate_list_items(sprint_insights['metrics']['issues_by_assignee'])}
                        </ul>
                    """,
                    "representation": "storage"
                }
            }
        }
        
        # Actualizar el documento
        update_response = requests.put(url, auth=confluence_auth, headers=headers, json=content)
        update_response.raise_for_status()
        
        return {
            "success": True,
            "message": "Documento de Confluence actualizado correctamente",
            "page_id": page_id,
            "new_version": current_version + 1
        }
        
    except requests.exceptions.RequestException as e:
        print(f"Error al actualizar el documento de Confluence: {e}")
        return {
            "success": False,
            "message": f"Error al actualizar el documento: {str(e)}",
            "page_id": page_id
        }

def generate_list_items(data_dict):
    """Genera elementos de lista HTML a partir de un diccionario"""
    return "".join([f"<li><strong>{key}:</strong> {value}</li>" for key, value in data_dict.items()])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)