package controlplane

import (
	"bytes"
	"context"
	"crypto/sha256"
	"embed"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"time"
)

//go:embed assets/agent.py
var agentFS embed.FS

type Options struct {
	ClusterName     string
	Model           string
	RecreateCluster bool
}

type ControlPlane struct {
	openRouterAPIKey string
	clusterName      string
	model            string
	recreateCluster  bool
}

func New(options Options) (*ControlPlane, error) {
	if options.ClusterName == "" {
		options.ClusterName = "dorothy-mvp"
	}
	if options.Model == "" {
		options.Model = "deepseek/deepseek-v3.2"
	}

	apiKey := os.Getenv("OPENROUTER_API_KEY")
	if apiKey == "" {
		return nil, errors.New("OPENROUTER_API_KEY is required")
	}

	return &ControlPlane{
		openRouterAPIKey: apiKey,
		clusterName:      options.ClusterName,
		model:            options.Model,
		recreateCluster:  options.RecreateCluster,
	}, nil
}

func (cp *ControlPlane) Initialize(ctx context.Context) error {
	if err := ensureCommand("kind"); err != nil {
		return err
	}
	if err := ensureCommand("kubectl"); err != nil {
		return err
	}
	if err := cp.ensureCluster(ctx); err != nil {
		return err
	}
	return cp.deployAgent(ctx)
}

func (cp *ControlPlane) SendMessage(ctx context.Context, message string) (map[string]any, error) {
	if strings.TrimSpace(message) == "" {
		return nil, errors.New("message is required")
	}
	if err := cp.Initialize(ctx); err != nil {
		return nil, err
	}

	portForward, err := cp.startPortForward(ctx, 18080)
	if err != nil {
		return nil, err
	}
	defer portForward.Stop()

	payload, err := json.Marshal(map[string]string{"message": message})
	if err != nil {
		return nil, err
	}

	request, err := http.NewRequestWithContext(ctx, http.MethodPost, "http://127.0.0.1:18080/chat", bytes.NewReader(payload))
	if err != nil {
		return nil, err
	}
	request.Header.Set("content-type", "application/json")

	client := &http.Client{Timeout: 90 * time.Second}
	response, err := client.Do(request)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()

	var result map[string]any
	if err := json.NewDecoder(response.Body).Decode(&result); err != nil {
		return nil, err
	}

	return result, nil
}

func (cp *ControlPlane) ensureCluster(ctx context.Context) error {
	output, err := run(ctx, "kind", "get", "clusters")
	if err != nil {
		return err
	}

	clusters := map[string]bool{}
	for _, cluster := range strings.Split(output, "\n") {
		cluster = strings.TrimSpace(cluster)
		if cluster != "" {
			clusters[cluster] = true
		}
	}

	if cp.recreateCluster && clusters[cp.clusterName] {
		if _, err := run(ctx, "kind", "delete", "cluster", "--name", cp.clusterName); err != nil {
			return err
		}
		delete(clusters, cp.clusterName)
	}

	if !clusters[cp.clusterName] {
		if _, err := run(ctx, "kind", "create", "cluster", "--name", cp.clusterName); err != nil {
			return err
		}
	}

	_, err = run(ctx, "kind", "export", "kubeconfig", "--name", cp.clusterName)
	return err
}

func (cp *ControlPlane) deployAgent(ctx context.Context) error {
	manifest, err := cp.agentManifest()
	if err != nil {
		return err
	}

	if _, err := runWithInput(ctx, manifest, "kubectl", "--context", cp.contextName(), "apply", "-f", "-"); err != nil {
		return err
	}

	_, err = run(
		ctx,
		"kubectl",
		"--context", cp.contextName(),
		"-n", "dorothy-system",
		"rollout", "status",
		"deployment/dorothy-agent",
		"--timeout=180s",
	)
	return err
}

func (cp *ControlPlane) agentManifest() (string, error) {
	agentScript, err := agentFS.ReadFile("assets/agent.py")
	if err != nil {
		return "", err
	}
	configHash := sha256.Sum256([]byte(string(agentScript) + cp.model + cp.openRouterAPIKey))

	return fmt.Sprintf(`apiVersion: v1
kind: Namespace
metadata:
  name: dorothy-system
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: dorothy-agent
  namespace: dorothy-system
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: dorothy-agent-health
rules:
  - nonResourceURLs:
      - /version
    verbs:
      - get
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: dorothy-agent-health
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: dorothy-agent-health
subjects:
  - kind: ServiceAccount
    name: dorothy-agent
    namespace: dorothy-system
---
apiVersion: v1
kind: Secret
metadata:
  name: dorothy-agent-openrouter
  namespace: dorothy-system
type: Opaque
stringData:
  OPENROUTER_API_KEY: %s
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: dorothy-agent-code
  namespace: dorothy-system
data:
  agent.py: |
%s---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dorothy-agent
  namespace: dorothy-system
spec:
  replicas: 1
  selector:
    matchLabels:
      app: dorothy-agent
  template:
    metadata:
      annotations:
        dorothydeploy/config-hash: %s
      labels:
        app: dorothy-agent
    spec:
      serviceAccountName: dorothy-agent
      containers:
        - name: agent
          image: python:3.12-slim
          imagePullPolicy: IfNotPresent
          command:
            - python
            - /app/agent.py
          env:
            - name: OPENROUTER_API_KEY
              valueFrom:
                secretKeyRef:
                  name: dorothy-agent-openrouter
                  key: OPENROUTER_API_KEY
            - name: OPENROUTER_MODEL
              value: %s
          ports:
            - name: http
              containerPort: 8080
          volumeMounts:
            - name: code
              mountPath: /app
      volumes:
        - name: code
          configMap:
            name: dorothy-agent-code
---
apiVersion: v1
kind: Service
metadata:
  name: dorothy-agent
  namespace: dorothy-system
spec:
  selector:
    app: dorothy-agent
  ports:
    - name: http
      port: 8080
      targetPort: http
`, strconv.Quote(cp.openRouterAPIKey), indentYAMLBlock(string(agentScript)), fmt.Sprintf("%x", configHash), strconv.Quote(cp.model)), nil
}

func (cp *ControlPlane) contextName() string {
	return "kind-" + cp.clusterName
}

func (cp *ControlPlane) startPortForward(ctx context.Context, localPort int) (*portForward, error) {
	processContext, cancel := context.WithCancel(ctx)
	command := exec.CommandContext(
		processContext,
		"kubectl",
		"--context", cp.contextName(),
		"-n", "dorothy-system",
		"port-forward",
		"service/dorothy-agent",
		fmt.Sprintf("%d:8080", localPort),
	)

	var output bytes.Buffer
	command.Stdout = &output
	command.Stderr = &output

	if err := command.Start(); err != nil {
		cancel()
		return nil, err
	}

	done := make(chan error, 1)
	go func() {
		done <- command.Wait()
	}()

	pf := &portForward{cancel: cancel, done: done}
	deadline := time.Now().Add(15 * time.Second)
	client := &http.Client{Timeout: time.Second}

	for time.Now().Before(deadline) {
		select {
		case <-done:
			cancel()
			return nil, fmt.Errorf("port-forward exited early: %s", output.String())
		default:
		}

		request, err := http.NewRequestWithContext(ctx, http.MethodGet, fmt.Sprintf("http://127.0.0.1:%d/health", localPort), nil)
		if err != nil {
			pf.Stop()
			return nil, err
		}

		response, err := client.Do(request)
		if err == nil {
			_ = response.Body.Close()
			return pf, nil
		}

		time.Sleep(250 * time.Millisecond)
	}

	pf.Stop()
	return nil, errors.New("timed out waiting for port-forward")
}

type portForward struct {
	cancel context.CancelFunc
	done   <-chan error
}

func (pf *portForward) Stop() {
	pf.cancel()
	<-pf.done
}

func ensureCommand(name string) error {
	if _, err := exec.LookPath(name); err != nil {
		return fmt.Errorf("required command not found: %s", name)
	}
	return nil
}

func run(ctx context.Context, name string, args ...string) (string, error) {
	return runWithInput(ctx, "", name, args...)
}

func runWithInput(ctx context.Context, input string, name string, args ...string) (string, error) {
	command := exec.CommandContext(ctx, name, args...)
	if input != "" {
		command.Stdin = strings.NewReader(input)
	}

	var output bytes.Buffer
	command.Stdout = &output
	command.Stderr = &output

	if err := command.Run(); err != nil {
		return output.String(), fmt.Errorf("%s %s failed: %w: %s", name, strings.Join(args, " "), err, output.String())
	}

	return output.String(), nil
}

func indentYAMLBlock(value string) string {
	var builder strings.Builder
	for _, line := range strings.Split(value, "\n") {
		builder.WriteString("    ")
		builder.WriteString(line)
		builder.WriteString("\n")
	}
	return builder.String()
}
