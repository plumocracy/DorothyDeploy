package main

import (
	"log"
	"os"

	"dorothydeploy/control-plane/internal/api"
)

func main() {
	if err := api.LoadDotEnv(".env"); err != nil {
		log.Fatalf("load .env: %v", err)
	}

	host := envOrDefault("CONTROL_PLANE_HOST", "127.0.0.1")
	port := envOrDefault("CONTROL_PLANE_PORT", "5000")
	addr := host + ":" + port

	server := api.NewServer()
	log.Printf("control plane listening on http://%s", addr)
	if err := server.ListenAndServe(addr); err != nil {
		log.Fatal(err)
	}
}

func envOrDefault(key string, fallback string) string {
	value := os.Getenv(key)
	if value == "" {
		return fallback
	}
	return value
}
