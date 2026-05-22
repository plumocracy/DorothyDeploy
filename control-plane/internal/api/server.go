package api

import (
	"encoding/json"
	"net/http"

	"dorothydeploy/control-plane/internal/controlplane"
)

type Server struct {
	mux *http.ServeMux
}

type initRequest struct {
	ClusterName     string `json:"cluster_name"`
	Model           string `json:"model"`
	RecreateCluster bool   `json:"recreate_cluster"`
}

type chatRequest struct {
	Message         string `json:"message"`
	ClusterName     string `json:"cluster_name"`
	Model           string `json:"model"`
	RecreateCluster bool   `json:"recreate_cluster"`
}

func NewServer() *Server {
	server := &Server{mux: http.NewServeMux()}
	server.mux.HandleFunc("GET /health", server.health)
	server.mux.HandleFunc("POST /init", server.init)
	server.mux.HandleFunc("POST /chat", server.chat)
	return server
}

func (s *Server) ListenAndServe(addr string) error {
	return http.ListenAndServe(addr, s.mux)
}

func (s *Server) health(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{
		"ok":      true,
		"service": "control-plane",
	})
}

func (s *Server) init(w http.ResponseWriter, r *http.Request) {
	var request initRequest
	if err := readJSON(r, &request); err != nil {
		writeJSON(w, http.StatusBadRequest, errorResponse(err))
		return
	}

	options := optionsFromRequest(request.ClusterName, request.Model, request.RecreateCluster)
	cp, err := controlplane.New(options)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, errorResponse(err))
		return
	}

	if err := cp.Initialize(r.Context()); err != nil {
		writeJSON(w, http.StatusInternalServerError, errorResponse(err))
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"ok":      true,
		"cluster": options.ClusterName,
	})
}

func (s *Server) chat(w http.ResponseWriter, r *http.Request) {
	var request chatRequest
	if err := readJSON(r, &request); err != nil {
		writeJSON(w, http.StatusBadRequest, errorResponse(err))
		return
	}
	if request.Message == "" {
		writeJSON(w, http.StatusBadRequest, map[string]any{"ok": false, "error": "message is required"})
		return
	}

	options := optionsFromRequest(request.ClusterName, request.Model, request.RecreateCluster)
	cp, err := controlplane.New(options)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, errorResponse(err))
		return
	}

	response, err := cp.SendMessage(r.Context(), request.Message)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, errorResponse(err))
		return
	}

	status := http.StatusOK
	if ok, _ := response["ok"].(bool); !ok {
		status = http.StatusBadGateway
	}
	writeJSON(w, status, response)
}

func optionsFromRequest(clusterName string, model string, recreateCluster bool) controlplane.Options {
	if clusterName == "" {
		clusterName = "dorothy-mvp"
	}
	if model == "" {
		model = "deepseek/deepseek-v3.2"
	}

	return controlplane.Options{
		ClusterName:     clusterName,
		Model:           model,
		RecreateCluster: recreateCluster,
	}
}

func readJSON(r *http.Request, target any) error {
	if r.Body == nil {
		return nil
	}
	defer r.Body.Close()

	if r.ContentLength == 0 {
		return nil
	}

	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	return decoder.Decode(target)
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("content-type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func errorResponse(err error) map[string]any {
	return map[string]any{"ok": false, "error": err.Error()}
}
