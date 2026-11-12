targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the the environment which is used to generate a short unique hash used in all resources.')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
param location string

@description('Name of the resource group')
param resourceGroupName string = ''

@description('API container image')
param apiImage string = ''

@description('Frontend container image')
param frontendImage string = ''

var abbrs = loadJsonContent('abbreviations.json')
var resourceToken = 'grubify'  // Fixed naming instead of random string
var uniqueSuffix = uniqueString(subscription().id, environmentName)
var tags = { 'azd-env-name': environmentName }
var http5xxAlertName = 'alert-grubify-api-http-5xx'

// Organize resources in a resource group
resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: !empty(resourceGroupName) ? resourceGroupName : 'rg-grubify-app'
  location: location
  tags: tags
}

// Container registry
module containerRegistry 'core/host/container-registry.bicep' = {
  name: 'container-registry'
  scope: rg
  params: {
    name: '${abbrs.containerRegistryRegistries}${resourceToken}${uniqueSuffix}'
    location: location
    tags: tags
  }
}

// Container Apps Environment
module containerAppsEnvironment 'core/host/container-apps-environment.bicep' = {
  name: 'container-apps-environment'
  scope: rg
  params: {
    name: '${abbrs.appManagedEnvironments}${resourceToken}'
    location: location
    tags: tags
  }
}

// Container app for the API
module api 'core/host/container-app.bicep' = {
  name: 'api'
  scope: rg
  params: {
    name: 'ca-grubify-api'
    location: location
    tags: union(tags, { 'azd-service-name': 'api' })
    containerAppsEnvironmentName: containerAppsEnvironment.outputs.name
    containerRegistryName: containerRegistry.outputs.name
    containerName: 'grubify-api'
    containerImage: !empty(apiImage) ? apiImage : 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
    targetPort: 8080
    external: true
    minReplicas: 1  // Always keep 1 instance running
    maxReplicas: 1  // No autoscaling - single instance only
    env: [
      {
        name: 'ASPNETCORE_ENVIRONMENT'
        value: 'Production'
      }
      {
        name: 'AllowedOrigins__0'
        value: 'https://ca-grubify-frontend.${containerAppsEnvironment.outputs.defaultDomain}'
      }
    ]
  }
}

// Container app for the frontend
module frontend 'core/host/container-app.bicep' = {
  name: 'frontend'
  scope: rg
  params: {
    name: 'ca-grubify-frontend'
    location: location
    tags: union(tags, { 'azd-service-name': 'frontend' })
    containerAppsEnvironmentName: containerAppsEnvironment.outputs.name
    containerRegistryName: containerRegistry.outputs.name
    containerName: 'grubify-frontend'
    containerImage: !empty(frontendImage) ? frontendImage : 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
    targetPort: 80
    external: true
    minReplicas: 1  // Always keep 1 instance running
    maxReplicas: 1  // No autoscaling - single instance only
    env: [
      {
        name: 'REACT_APP_API_BASE_URL'
        value: 'https://${api.outputs.fqdn}/api'
      }
    ]
  }
}

// Application Insights (workspace-based) used by the SRE Agent for its own telemetry
module appInsights 'core/monitor/applicationinsights.bicep' = {
  name: 'app-insights'
  scope: rg
  params: {
    name: '${abbrs.insightsComponents}${resourceToken}'
    location: location
    tags: tags
    logAnalyticsWorkspaceId: containerAppsEnvironment.outputs.logAnalyticsWorkspaceId
  }
}

// HTTP 5xx alert on the API: memory leak (Hot Deals) and payment failures (Grubify Pay) both fire it
module http5xxAlert 'core/monitor/http-5xx-alert.bicep' = {
  name: 'http-5xx-alert'
  scope: rg
  params: {
    name: http5xxAlertName
    containerAppId: api.outputs.id
    tags: tags
  }
}

// Azure SRE Agent that investigates the alert and files GitHub issues
module sreAgent 'core/ai/sre-agent.bicep' = {
  name: 'sre-agent'
  scope: rg
  params: {
    name: 'sre-grubify-${take(uniqueSuffix, 8)}'
    location: location
    tags: tags
    appInsightsId: appInsights.outputs.id
    appInsightsAppId: appInsights.outputs.appId
    appInsightsConnectionString: appInsights.outputs.connectionString
  }
}

// App outputs
output AZURE_LOCATION string = location
output AZURE_TENANT_ID string = tenant().tenantId
output AZURE_RESOURCE_GROUP string = rg.name
output RESOURCE_GROUP_ID string = rg.id

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerRegistry.outputs.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = containerRegistry.outputs.name

output API_BASE_URL string = 'https://${api.outputs.fqdn}'
output FRONTEND_URL string = 'https://${frontend.outputs.fqdn}'

output API_CONTAINER_APP_NAME string = 'ca-grubify-api'
output LOG_ANALYTICS_WORKSPACE_ID string = containerAppsEnvironment.outputs.logAnalyticsWorkspaceId
output APPLICATIONINSIGHTS_ID string = appInsights.outputs.id
output HTTP_5XX_ALERT_NAME string = http5xxAlert.outputs.name
output SRE_AGENT_ID string = sreAgent.outputs.id
output SRE_AGENT_NAME string = sreAgent.outputs.name
output SRE_AGENT_ENDPOINT string = sreAgent.outputs.endpoint
